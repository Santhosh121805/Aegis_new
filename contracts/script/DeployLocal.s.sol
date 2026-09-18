// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {AegisRegistry} from "../src/AegisRegistry.sol";
import {StubEscrow} from "../src/StubEscrow.sol";

/// @notice Local Anvil deployment. Deploys AegisRegistry and the StubEscrow stand-in, and
///         wires the oracle and the escrow. Run it through `python script/deploy_local.py`, which records the
///         addresses in deployments/local.json -- Foundry refuses to write outside contracts/.
///         Nothing downstream hardcodes an address; everything reads that file.
/// @dev Uses Anvil's default mnemonic, so the accounts are the ones `anvil` prints:
///        account 0  owner + scoreOracle (the oracle service signs with this key)
///        account 1  HonestAgent      account 2  SloppyAgent      account 3  demo hirer
///        account 9  seeder; agents/seed_demo.py borrows the escrow slot for it
///      `escrow` is StubEscrow, a stand-in. When the real AegisEscrow deploys, `setEscrow` MUST
///      point at it (SPEC.md section 6).
contract DeployLocal is Script {
    string internal constant ANVIL_MNEMONIC = "test test test test test test test test test test test junk";

    function run() external returns (AegisRegistry registry, StubEscrow escrow) {
        uint256 ownerKey = vm.deriveKey(ANVIL_MNEMONIC, 0);
        address owner = vm.addr(ownerKey);

        vm.startBroadcast(ownerKey);
        registry = new AegisRegistry(owner);
        registry.setScoreOracle(owner);
        escrow = new StubEscrow(registry);
        registry.setEscrow(address(escrow));
        vm.stopBroadcast();

        console2.log("AegisRegistry:", address(registry));
        console2.log("scoreOracle:  ", owner);
        console2.log("StubEscrow (stand-in):", address(escrow));
    }
}
