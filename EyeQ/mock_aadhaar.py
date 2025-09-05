import random
import numpy as np
from cryptography.fernet import Fernet

class MockAadhaarAPI:
    def __init__(self, encryption_key):
        self.cipher = Fernet(encryption_key)
        self.stored_iris_codes = {  # Encrypted stored codes
            "123456789012": self.cipher.encrypt(np.random.randint(0, 2, 64*512*4).astype(np.uint8).tobytes()),  # Longer code for multi-Gabor
        }
    
    def authenticate(self, aadhaar_number, encrypted_captured_code):
        if aadhaar_number not in self.stored_iris_codes:
            return False, "Aadhaar number not found."
        stored_encrypted = self.stored_iris_codes[aadhaar_number]
        stored_code = np.frombuffer(self.cipher.decrypt(stored_encrypted), dtype=np.uint8)
        captured_code = np.frombuffer(self.cipher.decrypt(encrypted_captured_code), dtype=np.uint8)
        distance = np.sum(np.bitwise_xor(stored_code, captured_code)) / len(stored_code)
        if distance < 0.32:
            return True, "Authentication successful."
        else:
            return False, "Iris does not match."
