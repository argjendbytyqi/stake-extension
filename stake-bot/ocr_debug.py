import cv2
import pytesseract
import os

def extract_code_from_video(video_path):
    if not os.path.exists(video_path):
        return "File not found"
    
    cap = cv2.VideoCapture(video_path)
    count = 0
    codes = []
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        # Check every 10th frame for speed
        if count % 10 == 0:
            # Focus on the middle-bottom area where codes usually appear
            height, width, _ = frame.shape
            # Crop to center/bottom (adjust based on template)
            roi = frame[int(height*0.3):int(height*0.8), int(width*0.1):int(width*0.9)]
            
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # Binary threshold to pop the text
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            
            text = pytesseract.image_to_string(thresh, config='--psm 6').strip()
            # Basic validation for Stake code pattern (often starts with 'stake')
            if text:
                codes.append(text)
        
        count += 1
        if count > 300: # Max 10 seconds at 30fps
            break
            
    cap.release()
    return codes

if __name__ == "__main__":
    v_path = "/home/argjend/Desktop/Stake.com Bonus Drop Template (3).mp4"
    results = extract_code_from_video(v_path)
    print(f"Debug OCR results: {results}")
