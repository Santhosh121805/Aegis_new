# Loads .env if present, so deploy targets pick up RPC URL and keys.
-include .env
export

.PHONY: build test deploy-sepolia clean fmt

build:
	forge build

test:
	forge test -vv

clean:
	forge clean

fmt:
	forge fmt

# Requires .env with BASE_SEPOLIA_RPC_URL, PRIVATE_KEY and ETHERSCAN_API_KEY.
# Copy .env.example to .env and fill it in. Never commit .env.
deploy-sepolia:
	forge script script/Deploy.s.sol:Deploy \
		--rpc-url $(BASE_SEPOLIA_RPC_URL) \
		--broadcast \
		--verify \
		-vvvv
