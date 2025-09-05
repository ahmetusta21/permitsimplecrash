from web3 import Web3
import json

# Connect to BSC
bsc_rpc = "https://data-seed-prebsc-1-s1.binance.org:8545"
web3 = Web3(Web3.HTTPProvider(bsc_rpc))

# Load Universal Router ABI
with open("universalrouter_abi.json") as f:
    universal_router_abi = json.load(f)

universal_router = web3.eth.contract(
    address=Web3.to_checksum_address("0xd77c2afebf3dc665af07588bf798bd938968c72e"),
    abi=universal_router_abi,
)

# Paste the PancakeSwap TX input
pancake_tx_input = 'https://testnet.bscscan.com/tx/0x9c755ccf681dec85d281529bd0ae1bdee7cad820160664eafe17e62828cd382f'  # full hex from BscScan
# Paste your Bot TX input
bot_tx_input = 'https://testnet.bscscan.com/tx/0x8d7e41f7b30360245123b4cc3336f4e07db93dda5c56d7ce826370cda322c21b'  # full hex from BscScan

# Decode PancakeSwap TX
func_pancake, args_pancake = universal_router.decode_function_input(pancake_tx_input)
print("PancakeSwap TX Decoded:")
print("Function:", func_pancake.fn_name)
print("Args:", args_pancake)

# Decode your Bot TX
func_bot, args_bot = universal_router.decode_function_input(bot_tx_input)
print("\nYour Bot TX Decoded:")
print("Function:", func_bot.fn_name)
print("Args:", args_bot)

# Extra: Print individual fields
print("\n--- PancakeSwap Details ---")
print(f"Commands: {args_pancake['commands'].hex()}")
for i, inp in enumerate(args_pancake['inputs']):
    print(f"Input {i}: {inp.hex()}")

print("\n--- Your Bot Details ---")
print(f"Commands: {args_bot['commands'].hex()}")
for i, inp in enumerate(args_bot['inputs']):
    print(f"Input {i}: {inp.hex()}")
