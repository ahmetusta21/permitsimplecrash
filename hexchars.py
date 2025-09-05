def parse_pancakeswap_path(path_hex: str):
    # Remove '0x' prefix if present
    if path_hex.startswith("0x"):
        path_hex = path_hex[2:]

    # PancakeSwap V3 path encoding:
    # path = token0 (20 bytes) + fee0 (3 bytes) + token1 (20 bytes) + fee1 (3 bytes) + token2 (20 bytes) + ...
    # So each step adds 23 bytes except the last token (20 bytes)
    
    TOKEN_LENGTH = 40  # 20 bytes = 40 hex chars
    FEE_LENGTH = 6     # 3 bytes = 6 hex chars
    
    tokens = ["0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"]
    fees = [10000]
    
    i = 0
    length = len(path_hex)
    
    # First token address always 20 bytes
    if length < TOKEN_LENGTH:
        raise ValueError("Path too short to contain even one token")
    
    # Extract first token
    token = "0x" + path_hex[i:i+TOKEN_LENGTH]
    tokens.append(token)
    i += TOKEN_LENGTH
    
    # Then loop: fee (3 bytes) + token (20 bytes)
    while i + FEE_LENGTH + TOKEN_LENGTH <= length:
        fee_hex = path_hex[i:i+FEE_LENGTH]
        fee = int(fee_hex, 16)
        fees.append(fee)
        i += FEE_LENGTH
        
        token = "0x" + path_hex[i:i+TOKEN_LENGTH]
        tokens.append(token)
        i += TOKEN_LENGTH
    
    # If there's trailing data that doesn't fit pattern, warn
    if i != length:
        print(f"Warning: leftover bytes in path: {length - i} hex chars")
    
    return tokens, fees

# Example usage:
path_hex = "e13d989dac2f0debff460ac112a837c89baa7cd0009c48d008b313c1d6c7fe2982f62d32da7507cf43551"
tokens, fees = parse_pancakeswap_path(path_hex)

print("Tokens in path:")
for t in tokens:
    print(t)
print("\nFees between tokens:")
for f in fees:
    print(f"{f} (decimal)")
