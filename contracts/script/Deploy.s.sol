// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {AegisRegistry} from "../src/AegisRegistry.sol";

/// @notice Deploys AegisRegistry and prints the address.
/// @dev The deployer becomes the owner. Set the score oracle and escrow addresses
///      afterwards with `setScoreOracle` / `setEscrow`.
contract Deploy is Script {
    function run() external returns (AegisRegistry registry) {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        vm.startBroadcast(deployerKey);
        registry = new AegisRegistry(deployer);
        vm.stopBroadcast();

        console2.log("");
        console2.log("=== AEGIS deployment ===");
        console2.log("chain id:        ", block.chainid);
        console2.log("deployer/owner:  ", deployer);
        console2.log("AegisRegistry:   ", address(registry));
        console2.log("");
        console2.log("Next: set the oracle and escrow addresses.");
        console2.log("  cast send <registry> 'setScoreOracle(address)' <oracle>");
        console2.log("  cast send <registry> 'setEscrow(address)' <escrow>");
        console2.log("");
    }
}
