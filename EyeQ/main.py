import tkinter as tk
from tkinter import ttk, messagebox, Menu
from ttkthemes import ThemedTk
from PIL import Image, ImageTk, ImageDraw
import cv2
import numpy as np
from iris_recognition import EyeQRecognizer
from mock_aadhaar import MockAadhaarAPI
import threading

class EyeQApp:
    def __init__(self, root):
        self.root = root
        self.root.title("EyeQ - Advanced Iris Authentication")
        self.root.geometry("900x700")
        self.root.configure(bg="#f0f0f0")
        
        self.recognizer = EyeQRecognizer()
        self.aadhaar_api = MockAadhaarAPI(self.recognizer.encryption_key)
        
        # Modern style
        style = ttk.Style()
        style.configure("TLabel", font=("Helvetica", 12), background="#f0f0f0")
        style.configure("TButton", font=("Helvetica", 12, "bold"), padding=10)
        style.configure("TEntry", font=("Helvetica", 12))
        style.map("TButton", background=[("active", "#4CAF50")])
        
        # Menu bar
        menubar = Menu(self.root)
        helpmenu = Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.root.config(menu=menubar)
        
        # UI Elements
        ttk.Label(self.root, text="EyeQ: Secure Iris Auth for Markets", font=("Helvetica", 16, "bold")).pack(pady=10)
        
        self.aadhaar_entry = ttk.Entry(self.root, width=50)
        self.aadhaar_entry.pack(pady=5)
        self.aadhaar_entry.insert(0, "Enter Aadhaar Number")
        
        self.video_label = tk.Label(self.root, bg="#ffffff", borderwidth=2, relief="solid")
        self.video_label.pack(pady=10)
        
        self.feedback_label = ttk.Label(self.root, text="", foreground="red")
        self.feedback_label.pack(pady=5)
        
        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=300)
        self.progress.pack(pady=10)
        
        btn_frame = tk.Frame(self.root, bg="#f0f0f0")
        btn_frame.pack(pady=10)
        self.capture_btn = ttk.Button(btn_frame, text="Capture & Authenticate", command=self.capture)
        self.capture_btn.grid(row=0, column=0, padx=10)
        
        self.status_label = ttk.Label(self.root, text="Status: Ready")
        self.status_label.pack(pady=10)
        
        # Video capture
        self.cap = cv2.VideoCapture(0)
        self.frame_buffer = []
        self.buffer_size = 60  # Increased for better liveness
        self.show_video()
    
    def show_about(self):
        messagebox.showinfo("About EyeQ", "Advanced iris auth tool for SEBI Hackathon.\nFeatures: Distant capture, liveness, encryption.")
    
    def draw_overlays(self, frame, eye_regions):
        for _, (ex, ey, ew, eh) in eye_regions:
            cv2.rectangle(frame, (ex, ey), (ex+ew, ey+eh), (0, 255, 0), 2)
            # Iris approx circle (simplified)
            cv2.circle(frame, (ex + ew//2, ey + eh//2), eh//2, (255, 0, 0), 1)
        return frame
    
    def show_video(self):
        ret, frame = self.cap.read()
        if ret:
            _, eye_regions, _ = self.recognizer.detect_face_and_eyes(frame)
            frame_with_overlay = self.draw_overlays(frame, eye_regions)
            frame_rgb = cv2.cvtColor(frame_with_overlay, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb).resize((640, 480))
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
            
            self.frame_buffer.append(frame)
            if len(self.frame_buffer) > self.buffer_size:
                self.frame_buffer.pop(0)
        
        self.root.after(10, self.show_video)
    
    def capture(self):
        threading.Thread(target=self._capture_thread).start()
    
    def _capture_thread(self):
        self.progress.start()
        self.status_label.config(text="Status: Processing...")
        self.capture_btn.config(state="disabled")
        
        consent = messagebox.askyesno("Consent", "Consent to biometric capture? Data processed in-memory only.")
        if not consent:
            self._reset_ui("Status: Consent denied.")
            return
        
        if not self.recognizer.check_liveness(self.frame_buffer):
            self._reset_ui("Status: Liveness failed. Blink and move eyes.")
            return
        
        ret, frame = self.cap.read()
        if not ret:
            self._reset_ui("Status: Capture failed.")
            return
        
        iris_code, eye_regions, feedback = self.recognizer.process_iris(frame)
        if iris_code is None:
            self._reset_ui(f"Status: {feedback}")
            return
        
        if feedback:
            self.feedback_label.config(text=feedback)
        
        encrypted_code = self.recognizer.encrypt_iris_code(iris_code)
        aadhaar_num = self.aadhaar_entry.get()
        success, message = self.aadhaar_api.authenticate(aadhaar_num, encrypted_code)
        
        if success:
            self._reset_ui(f"Status: {message} - Access Granted.", success=True)
            messagebox.showinfo("Success", "Authenticated! Welcome.")
        else:
            self._reset_ui(f"Status: {message} - Access Denied.")
            messagebox.showerror("Failure", message)
    
    def _reset_ui(self, status, success=False):
        self.progress.stop()
        self.status_label.config(text=status, foreground="green" if success else "red")
        self.capture_btn.config(state="normal")
        self.feedback_label.config(text="")
    
    def __del__(self):
        self.cap.release()

if __name__ == "__main__":
    root = ThemedTk(theme="arc")  # Modern theme
    app = EyeQApp(root)
    root.mainloop()
