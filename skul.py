from web3 import Web3
import json
import time
from eth_abi import encode
from eth_utils import keccak
from eth_account import Account
import config
import requests  # Added for BNB/USD price fetch

"""
Integrated PancakeSwap Universal Router + Permit2 bot with sniping functionality
- Checks for an active pool with liquidity
- Fetches BNB/USD price to calculate token price
- Uses Permit2 for secure token approvals
- Executes V3 swap via Universal Router
"""

# --- CONFIG ---
BSC_TESTNET_URL = "https://data-seed-prebsc-1-s1.binance.org:8545"
CHAIN_ID = 97
PRIVATE_KEY = config.private
ACCOUNT = Account.from_key(PRIVATE_KEY)
SENDER_ADDRESS = ACCOUNT.address

# PancakeSwap V3 Testnet Addresses
WBNB_ADDRESS = Web3.to_checksum_address("0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd")
QUOTER_ADDRESS = Web3.to_checksum_address("0xbC203d7f83677c7ed3F7acEc959963E7F4ECC5C2")
FACTORY_ADDRESS = Web3.to_checksum_address("0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865")
UNIVERSAL_ROUTER_ADDRESS = Web3.to_checksum_address("0x87FD5305E6a40F378da124864B2D479c2028BD86")
PERMIT2_ADDRESS = Web3.to_checksum_address("0x31c2F6fcFf4F8759b3Bd5Bf0e1084A055615c768")

# User Inputs
token_to_buy = Web3.to_checksum_address("0x8d008B313C1d6C7fE2982F62d32Da7507cF43551")
USD_BUDGET = 0.12  # USD budget to spend
MAX_TOKEN_PRICE_USD = 7.97813936  # Max allowed token price in USD
CHECK_INTERVAL = 0.5  # Seconds to wait between price checks
FEE_TIERS = [2500, 500, 10000]  # Fee tiers to check for active pool

# --- INIT WEB3 ---
web3 = Web3(Web3.HTTPProvider(BSC_TESTNET_URL))
assert web3.is_connected(), "Could not connect to BSC Testnet"
print("✅ Connected to BSC Testnet")

# --- LOAD ABIs ---
with open('quoterv2_abi.json') as f:
    quoter_abi = json.load(f)
with open('pancakeswapv3factory_abi.json') as f:
    factory_abi = json.load(f)
with open('universalrouter_abi.json') as f:
    universal_router_abi = json.load(f)
with open('ercs_abi.json') as f:
    erc20_abi = json.load(f)
with open('permits_abi.json') as f:
    permit2_abi = json.load(f)

# --- CONTRACTS ---
quoter = web3.eth.contract(address=QUOTER_ADDRESS, abi=quoter_abi)
factory = web3.eth.contract(address=FACTORY_ADDRESS, abi=factory_abi)
universal_router = web3.eth.contract(address=UNIVERSAL_ROUTER_ADDRESS, abi=universal_router_abi)
wbnb = web3.eth.contract(address=WBNB_ADDRESS, abi=erc20_abi)
token_contract = web3.eth.contract(address=token_to_buy, abi=erc20_abi)
permit2 = web3.eth.contract(address=PERMIT2_ADDRESS, abi=permit2_abi)

# --- HELPERS: EIP-712 hashing for Permit2 (AllowanceTransfer) ---
PERMIT_DETAILS_TYPE = "PermitDetails(address token,uint160 amount,uint48 expiration,uint48 nonce)"
PERMIT_SINGLE_TYPE = (
    "PermitSingle(PermitDetails details,address spender,uint256 sigDeadline)" +
    PERMIT_DETAILS_TYPE
)
PERMIT_DETAILS_TYPEHASH = keccak(text=PERMIT_DETAILS_TYPE)
PERMIT_SINGLE_TYPEHASH = keccak(text=PERMIT_SINGLE_TYPE)

def hash_permit_details(token: str, amount: int, expiration: int, nonce: int) -> bytes:
    return keccak(
        encode(
            ["bytes32", "address", "uint160", "uint48", "uint48"],
            [PERMIT_DETAILS_TYPEHASH, token, amount, expiration, nonce]
        )
    )

def hash_permit_single(details_hash: bytes, spender: str, sig_deadline: int) -> bytes:
    return keccak(
        encode(
            ["bytes32", "bytes32", "address", "uint256"],
            [PERMIT_SINGLE_TYPEHASH, details_hash, spender, sig_deadline]
        )
    )

def sign_eip712_with_domain_separator(domain_separator: bytes, struct_hash: bytes):
    digest = keccak(b"\x19\x01" + domain_separator + struct_hash)
    return Account._sign_hash(digest, private_key=PRIVATE_KEY)

# --- FUNCTION TO FIND ACTIVE POOL ---
def find_active_pool():
    for fee in FEE_TIERS:
        pool_candidate = factory.functions.getPool(WBNB_ADDRESS, token_to_buy, fee).call()
        if pool_candidate != "0x0000000000000000000000000000000000000000":
            wbnb_liquidity = wbnb.functions.balanceOf(pool_candidate).call()
            token_liquidity = token_contract.functions.balanceOf(pool_candidate).call()
            if wbnb_liquidity > 0 and token_liquidity > 0:
                print(f"✅ Active pool found at {pool_candidate} with fee {fee}")
                return pool_candidate, fee
    return None, None

# --- GET BNB/USD PRICE ---
def get_bnb_usd_price():
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd")
        data = response.json()
        price = data["binancecoin"]["usd"]
        print(f"BNB/USD price: ${price}")
        return price
    except Exception as e:
        print(f"❌ Failed to get BNB/USD price: {e}")
        return None

# --- WAIT FOR POOL WITH LIQUIDITY ---
while True:
    pool_address, FEE = find_active_pool()
    if pool_address:
        break
    print(f"Pool not active yet, retrying in {CHECK_INTERVAL} seconds...")
    time.sleep(CHECK_INTERVAL)

# --- GET BNB/USD PRICE ---
bnb_usd_price = get_bnb_usd_price()
if bnb_usd_price is None:
    print("❌ Aborting due to failure to fetch BNB/USD price")
    exit()

# --- CALCULATE AMOUNT TO SPEND ---
amount_in_ether = USD_BUDGET / bnb_usd_price
amount_in = web3.to_wei(amount_in_ether, 'ether')

# --- CHECK WBNB BALANCE ---
balance = wbnb.functions.balanceOf(SENDER_ADDRESS).call()
print(f"💰 WBNB Balance: {web3.from_wei(balance, 'ether')}")
if balance < amount_in:
    print(f"❌ Not enough WBNB to spend ${USD_BUDGET}. Balance: {web3.from_wei(balance, 'ether')} WBNB")
    exit()

# --- GET TOKEN DECIMALS ---
decimals = token_contract.functions.decimals().call()
print(f"Token decimals: {decimals}")

# --- CHECK POOL LIQUIDITY AGAIN ---
wbnb_liquidity = wbnb.functions.balanceOf(pool_address).call()
token_liquidity = token_contract.functions.balanceOf(pool_address).call()
print(f"Pool liquidity - WBNB: {web3.from_wei(wbnb_liquidity, 'ether')}, Token: {token_liquidity / (10 ** decimals)}")
if wbnb_liquidity == 0 or token_liquidity == 0:
    print("⚠️ Pool has no liquidity. Aborting.")
    exit()

# --- Read current AllowanceTransfer state ---
allow_struct = permit2.functions.allowance(SENDER_ADDRESS, WBNB_ADDRESS, UNIVERSAL_ROUTER_ADDRESS).call()
allowed_amount, allowed_exp, current_nonce = allow_struct
print(f"🔑 allowance.nonce = {current_nonce}")

# --- Build PermitSingle ---
max_uint160 = (1 << 160) - 1
permit_expiration = int(time.time()) + 7 * 24 * 60 * 60  # 7 days
sig_deadline = int(time.time()) + 1800  # 30 minutes

details_hash = hash_permit_details(WBNB_ADDRESS, max_uint160, permit_expiration, current_nonce)
struct_hash = hash_permit_single(details_hash, UNIVERSAL_ROUTER_ADDRESS, sig_deadline)
onchain_domain_separator = permit2.functions.DOMAIN_SEPARATOR().call()
print(f"🔑 DOMAIN_SEPARATOR(on-chain) = {onchain_domain_separator.hex()}")

signed = sign_eip712_with_domain_separator(onchain_domain_separator, struct_hash)
v = signed.v if signed.v >= 27 else signed.v + 27
signature = signed.r.to_bytes(32, 'big') + signed.s.to_bytes(32, 'big') + bytes([v])
print(f"🖊️ Signature (65b): {signature.hex()}")

# --- Dry-run Permit2.permit() ---
permit_details_tuple = (WBNB_ADDRESS, max_uint160, permit_expiration, current_nonce)
permit_single_tuple = (permit_details_tuple, UNIVERSAL_ROUTER_ADDRESS, sig_deadline)
try:
    permit2.functions.permit(SENDER_ADDRESS, permit_single_tuple, signature).call({'from': SENDER_ADDRESS})
    print("✅ Permit2.permit() staticcall OK")
except Exception as e:
    print("❌ Permit2.permit() staticcall reverted:", e)
    raise SystemExit(1)

# --- MAIN PRICE CHECK LOOP ---
while True:
    try:
        quote = quoter.functions.quoteExactInputSingle({
            'tokenIn': WBNB_ADDRESS,
            'tokenOut': token_to_buy,
            'amountIn': amount_in,
            'fee': FEE,
            'sqrtPriceLimitX96': 0
        }).call()
        amount_out = quote[0]
    except Exception as e:
        print(f"❌ Quote failed: {e}")
        time.sleep(CHECK_INTERVAL)
        continue

    token_amount = amount_out / (10 ** decimals)
    token_usd_price = (amount_in_ether * bnb_usd_price) / token_amount
    print(f"📊 Token price: ${token_usd_price:.8f}")

    if token_usd_price > MAX_TOKEN_PRICE_USD:
        print(f"⏳ Token price ${token_usd_price:.8f} too high. Waiting {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)
        continue

    print("✅ Price acceptable, executing buy...")
    amount_out_min = int(amount_out * 0.8)  # 20% slippage buffer
    print(f"🔄 Expected out min: {amount_out_min / (10 ** decimals)}")

    # --- Build UniversalRouter commands & inputs ---
    PERMIT2_PERMIT = 0x0a
    V3_SWAP_EXACT_IN = 0x00
    commands = bytes([PERMIT2_PERMIT, V3_SWAP_EXACT_IN])

    permit_input = encode(
        ["((address,uint160,uint48,uint48),address,uint256)", "bytes"],
        [permit_single_tuple, signature]
    )

    path = (
        bytes.fromhex(WBNB_ADDRESS[2:]) +
        FEE.to_bytes(3, 'big') +
        bytes.fromhex(token_to_buy[2:])
    )

    swap_input = encode(
        ["address", "uint256", "uint256", "bytes", "bool"],
        [SENDER_ADDRESS, amount_in, amount_out_min, path, True]
    )

    inputs = [permit_input, swap_input]

    # --- Approve Permit2 for WBNB if needed ---
    allowance_erc20 = wbnb.functions.allowance(SENDER_ADDRESS, PERMIT2_ADDRESS).call()
    if allowance_erc20 < amount_in:
        print("🔐 Approving Permit2 on WBNB...")
        tx = wbnb.functions.approve(PERMIT2_ADDRESS, 2**256 - 1).build_transaction({
            'from': SENDER_ADDRESS,
            'nonce': web3.eth.get_transaction_count(SENDER_ADDRESS),
            'gas': 60000,
            'gasPrice': web3.eth.gas_price,
        })
        signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        assert receipt.status == 1, "approve() failed"
        print("✅ ERC20 approve(Permit2) done")

    # --- Send Transaction ---
    deadline = int(time.time()) + 300
    try:
        gas_est = universal_router.functions.execute(commands, inputs, deadline).estimate_gas({
            'from': SENDER_ADDRESS,
            'value': 0
        })
        gas_limit = int(gas_est * 1.2)
        print(f"⛽ Gas estimate: {gas_est}")
    except Exception as e:
        print("⚠️ Gas estimation failed (will fallback to 500k):", e)
        gas_limit = 500000

    tx = universal_router.functions.execute(commands, inputs, deadline).build_transaction({
        'from': SENDER_ADDRESS,
        'nonce': web3.eth.get_transaction_count(SENDER_ADDRESS),
        'gas': gas_limit,
        'gasPrice': web3.eth.gas_price,
    })

    signed_tx = web3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    print("📤 Sending execute()...")
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print("🔗 Tx:", web3.to_hex(tx_hash))
    rcpt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print("✅ Status:", "Success" if rcpt.status == 1 else "Failed")

    # --- Post-check: AllowanceTransfer nonce ---
    post_allow = permit2.functions.allowance(SENDER_ADDRESS, WBNB_ADDRESS, UNIVERSAL_ROUTER_ADDRESS).call()
    print(f"🔁 New allowance.nonce = {post_allow[2]}")

    break  # ✅ stop after successful buy