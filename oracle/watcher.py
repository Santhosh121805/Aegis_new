"""AEGIS score oracle.

Loop: poll the Registry for OutcomeRecorded since the last processed block -> take that
agent's accumulated history -> POST /score/from-events -> updateScore(agent, score, reason).

Plain polling, no websocket subscriptions: Anvil restarts constantly during development and a
poll loop recovers from that by itself. On any restart, crash or dropped connection the
oracle starts a fresh session, which replays history from block 0 and rescores any agent
whose latest outcome is newer than its latest score update. Nothing is lost because the chain
is the only store.

Usage (from the repo root, with anvil, the score service and a local deploy running):
    oracle/.venv/Scripts/python oracle/watcher.py      # Windows
    oracle/.venv/bin/python oracle/watcher.py          # macOS / Linux
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests
from web3 import Web3

from config import Config, ConfigError, load_config
from history import History, Outcome
from reasons import build_reason
from writer import ScoreWriter

log = logging.getLogger("oracle")

RETRY_SECONDS = 3.0


class ChainReset(Exception):
    """The chain under us is not the one we replayed. Anvil restarted."""


class ScoreServiceError(Exception):
    """POST /score/from-events failed. Kept apart from requests errors web3 raises for RPC."""


class Session:
    """One connection to one chain. Discarded wholesale on any reset."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 10}))
        if not self.w3.is_connected():
            raise ConnectionError(f"no RPC at {config.rpc_url}")

        address = Web3.to_checksum_address(config.registry_address)
        if self.w3.eth.get_code(address) in (b"", None):
            raise ConfigError(
                f"No contract at {address} (from deployments/local.json). Anvil was probably "
                "restarted. Redeploy:\n    cd contracts && python script/deploy_local.py"
            )

        self.registry = self.w3.eth.contract(address=address, abi=config.registry_abi)
        self.writer = ScoreWriter(self.w3, self.registry, config.oracle_private_key)
        self.writer.verify_oracle()

        self.history = History()
        self._timestamps: dict[int, datetime] = {}
        self.last_block = -1
        self.last_block_hash: bytes | None = None

    # -- chain reads ------------------------------------------------------

    def _block_time(self, number: int) -> datetime:
        if number not in self._timestamps:
            block = self.w3.eth.get_block(number)
            self._timestamps[number] = datetime.fromtimestamp(block.timestamp, tz=timezone.utc)
        return self._timestamps[number]

    def _outcomes(self, from_block: int, to_block: int) -> list[Outcome]:
        logs = self.registry.events.OutcomeRecorded().get_logs(
            from_block=from_block, to_block=to_block
        )
        scale = 10**self.config.value_decimals
        return [
            Outcome(
                agent=entry.args.agent,
                delivered=entry.args.delivered,
                disputed=entry.args.disputed,
                value=entry.args.value,
                # The service requires a positive value; a zero-value job becomes one unit.
                value_usd=max(entry.args.value, 1) / scale,
                timestamp=self._block_time(entry.blockNumber),
                block_number=entry.blockNumber,
                log_index=entry.logIndex,
            )
            for entry in logs
        ]

    def _mark(self, head: int) -> None:
        self.last_block = head
        self.last_block_hash = bytes(self.w3.eth.get_block(head).hash)

    def _check_same_chain(self, head: int) -> None:
        # A restarted Anvil can overtake our height again within seconds, so a height check
        # alone misses resets. The hash of the last block we processed must still match.
        if head < self.last_block:
            raise ChainReset(f"head {head} is behind last processed block {self.last_block}")
        if bytes(self.w3.eth.get_block(self.last_block).hash) != self.last_block_hash:
            raise ChainReset(f"block {self.last_block} changed hash")

    # -- scoring ----------------------------------------------------------

    def rescore(self, trigger: Outcome) -> None:
        agent = trigger.agent

        url = f"{self.config.score_url}/score/from-events"
        try:
            response = requests.post(
                url, json=self.history.score_request(agent, as_of=trigger.timestamp), timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ScoreServiceError(f"{url}: {exc}") from exc
        result = response.json()

        old_score = self.writer.current_score(agent)
        new_score = result["score"]
        top_factor = result["top_factors"][0] if result["top_factors"] else None
        reason = build_reason(
            trigger,
            job_number=self.history.jobs_completed(agent),
            delta=new_score - old_score,
            top_factor=top_factor,
        )

        tx_hash = self.writer.update_score(agent, new_score, reason)

        log.info("%s  %d -> %d  %s", agent, old_score, new_score, reason)
        log.info("    features %s", result["derived_features"])
        log.info("    tx %s", tx_hash)

    # -- lifecycle --------------------------------------------------------

    def replay(self) -> None:
        """Rebuild history from block 0, then catch up agents the oracle missed."""
        head = self.w3.eth.block_number
        outcomes = self._outcomes(0, head)
        for outcome in outcomes:
            self.history.add(outcome)

        last_scored: dict[str, tuple[int, int]] = {}
        for entry in self.registry.events.ScoreUpdated().get_logs(from_block=0, to_block=head):
            last_scored[entry.args.agent] = (entry.blockNumber, entry.logIndex)

        stale = [
            self.history.outcomes(agent)[-1]
            for agent in self.history.agents()
            if self.history.outcomes(agent)[-1].position > last_scored.get(agent, (-1, -1))
        ]

        log.info(
            "Registry %s  oracle %s  replayed %d outcomes for %d agents up to block %d",
            self.registry.address, self.writer.account.address,
            len(outcomes), len(self.history.agents()), head,
        )
        for latest in stale:
            log.info("catching up %s (outcome at block %d never scored)", latest.agent, latest.block_number)
            self.rescore(latest)

        self._mark(head)

    def poll_forever(self) -> None:
        log.info("Watching for OutcomeRecorded every %.1fs", self.config.poll_interval)
        while True:
            time.sleep(self.config.poll_interval)
            head = self.w3.eth.block_number
            self._check_same_chain(head)
            if head == self.last_block:
                continue

            for outcome in self._outcomes(self.last_block + 1, head):
                self.history.add(outcome)
                self.rescore(outcome)

            # Mark only what was scanned. Our own updateScore blocks get rescanned next tick,
            # harmlessly; marking the newer head could skip an outcome that landed meanwhile.
            self._mark(head)


def main() -> None:
    logging.basicConfig(format="%(asctime)s  %(message)s", datefmt="%H:%M:%S", level=logging.INFO)

    last_error = None
    while True:
        try:
            session = Session(load_config())
            session.replay()
            last_error = None
            session.poll_forever()
        except ChainReset as exc:
            log.info("Chain reset (%s). Replaying from block 0.", exc)
            continue
        except ConfigError as exc:
            error = str(exc)
        except ScoreServiceError as exc:
            error = f"Score service unreachable or failing: {exc}"
        except (ConnectionError, requests.exceptions.ConnectionError) as exc:
            error = f"RPC unreachable: {exc}"
        except KeyboardInterrupt:
            return
        except Exception as exc:  # noqa: BLE001 -- the loop must survive anything and retry
            error = f"{type(exc).__name__}: {exc}"

        # Say it once, then retry quietly until something changes.
        if error != last_error:
            log.error("%s\nRetrying every %.0fs.", error, RETRY_SECONDS)
            last_error = error
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    main()
