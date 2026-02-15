import cv2
import pytesseract
import os
import sys

def extract_code_from_video(video_path):
    if not os.path.exists(video_path):
        return None
    
    cap = cv2.VideoCapture(video_path)
    frames_to_check = [0, 15, 30, 45, 60, 75, 90] # Sample every 0.5s if 30fps
    
    found_codes = []
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        frame_id = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        
        # Simple sampling for speed
        if frame_id % 15 == 0:
            # Pre-process: grayscale and thresholding for better OCR
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            
            text = pytesseract.image_to_string(thresh, config='--psm 7').strip()
            if text and len(text) > 4:
                found_codes.append(text)
                
    cap.release()
    
    # Return most frequent or longest string found as a heuristic
    if found_codes:
        return max(set(found_codes), key=found_codes.count)
    return None

if __name__ == "__main__":
    test_video = "/home/argjend/Desktop/Stake.com Bonus Drop Template (3).mp4"
    code = extract_code_from_video(test_video)
    print(f"Extracted Code: {code}")
