import cv2
import numpy as np
import torch  # Used for tensor operations in averaging
import math
from cryptography.fernet import Fernet

class EyeQRecognizer:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        self.iris_size = (64, 512)
        self.hamming_threshold = 0.32
        self.encryption_key = Fernet.generate_key()  # In prod: secure key management
        self.cipher = Fernet(self.encryption_key)
    
    def enhance_image(self, image):
        if len(image.shape) > 2:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))  # Increased clip for better contrast
        enhanced = clahe.apply(gray)
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        upscaled = cv2.resize(sharpened, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)  # Better interp
        # Noise reduction
        denoised = cv2.fastNlMeansDenoising(upscaled, None, 10, 7, 21)
        return denoised
    
    def detect_face_and_eyes(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        if len(faces) == 0:
            return None, [], None
        face = faces[0]  # Assume primary face
        roi_gray = gray[face[1]:face[1]+face[3], face[0]:face[0]+face[2]]
        eyes = self.eye_cascade.detectMultiScale(roi_gray, 1.1, 3)
        eye_regions = []
        for (ex, ey, ew, eh) in eyes:
            eye = frame[face[1]+ey:face[1]+ey+eh, face[0]+ex:face[0]+ex+ew]
            eye_regions.append((eye, (face[0]+ex, face[1]+ey, ew, eh)))
        return face, eye_regions, gray
    
    def segment_iris(self, eye_image):
        enhanced_eye = self.enhance_image(eye_image)
        edges = cv2.Canny(enhanced_eye, 30, 100)  # Adjusted thresholds for better edges
        circles = cv2.HoughCircles(edges, cv2.HOUGH_GRADIENT_ALT, dp=1.5, minDist=20,
                                   param1=300, param2=0.85, minRadius=5, maxRadius=60)  # Advanced Hough
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            if len(circles) >= 2:
                circles = sorted(circles, key=lambda c: c[2])
                pupil = circles[0]
                iris = circles[-1]
                mask = np.zeros_like(enhanced_eye)
                cv2.circle(mask, (iris[0], iris[1]), iris[2], 255, -1)
                cv2.circle(mask, (pupil[0], pupil[1]), pupil[2], 0, -1)
                iris_region = cv2.bitwise_and(enhanced_eye, enhanced_eye, mask=mask)
                return iris_region, iris[0], iris[1], iris[2], pupil[2]
        return None, None, None, None, None
    
    def normalize_iris(self, eye_image, cx, cy, iris_r, pupil_r):
        normalized = np.zeros(self.iris_size, dtype=np.uint8)
        for i in range(self.iris_size[1]):
            theta = (i / self.iris_size[1]) * 2 * np.pi
            for j in range(self.iris_size[0]):
                r = pupil_r + (j / self.iris_size[0]) * (iris_r - pupil_r)
                x = int(cx + r * math.cos(theta))
                y = int(cy + r * math.sin(theta))
                if 0 <= x < eye_image.shape[1] and 0 <= y < eye_image.shape[0]:
                    normalized[j, i] = eye_image[y, x]
        return normalized
    
    def extract_features(self, normalized):
        # Multi-orientation Gabor (advanced: 4 directions)
        kernels = []
        for theta in [0, np.pi/4, np.pi/2, 3*np.pi/4]:
            kernel = cv2.getGaborKernel((21, 21), 8.0, theta, 10.0, 0.5, 0, ktype=cv2.CV_32F)
            kernels.append(kernel)
        features = []
        for kernel in kernels:
            filtered = cv2.filter2D(normalized, cv2.CV_8UC3, kernel)
            binary = (filtered > 0).astype(np.uint8).flatten()
            features.append(binary)
        iris_code = np.concatenate(features)
        return iris_code
    
    def encrypt_iris_code(self, code):
        return self.cipher.encrypt(code.tobytes())
    
    def decrypt_iris_code(self, encrypted):
        return np.frombuffer(self.cipher.decrypt(encrypted), dtype=np.uint8)
    
    def compare_iris_codes(self, code1, code2):
        if len(code1) != len(code2):
            return 1.0
        xor = np.bitwise_xor(code1, code2)
        distance = np.sum(xor) / len(code1)
        return distance
    
    def process_iris(self, frame):
        face, eye_regions, gray = self.detect_face_and_eyes(frame)
        if face is None or len(eye_regions) < 2:
            return None, None, "Insufficient eyes detected. Ensure both eyes are visible."
        
        iris_codes = []
        for eye, _ in eye_regions:
            iris_region, cx, cy, iris_r, pupil_r = self.segment_iris(eye)
            if iris_region is None:
                continue
            normalized = self.normalize_iris(iris_region, cx, cy, iris_r, pupil_r)
            iris_code = self.extract_features(normalized)
            iris_codes.append(iris_code)
        
        if len(iris_codes) == 0:
            return None, None, "Iris segmentation failed."
        
        # Average codes (advanced: tensor mean)
        iris_codes_tensor = torch.tensor(iris_codes, dtype=torch.float32)
        avg_code = torch.mean(iris_codes_tensor, dim=0).round().numpy().astype(np.uint8)
        
        # Checks
        avg_intensity = np.mean(gray)
        face_area = face[2] * face[3]
        feedback = ""
        if avg_intensity < 100:
            feedback += "Improve lighting. "
        if face_area < 200*200:  # Arbitrary threshold for distance
            feedback += "Move closer to camera."
        
        return avg_code, eye_regions, feedback.strip()
    
    def check_liveness(self, frames):
        eye_positions = []
        for frame in frames:
            _, eye_regions, _ = self.detect_face_and_eyes(frame)
            if eye_regions:
                eye_pos = [region[1][:2] for region in eye_regions]  # (x,y) of eyes
                eye_positions.append(eye_pos)
        
        # Blink: variation in eye count
        eye_counts = [len(pos) for pos in eye_positions]
        blink_detected = len(set(eye_counts)) > 1
        
        # Movement: variance in positions
        if len(eye_positions) > 1 and eye_positions[0]:
            pos_array = np.array([pos[0] for pos in eye_positions if pos])  # First eye
            movement_var = np.var(pos_array, axis=0).sum()
            movement_detected = movement_var > 10  # Threshold for movement
        
        return blink_detected and movement_detected
