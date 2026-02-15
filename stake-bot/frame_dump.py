import cv2
import os

def save_frames(video_path, output_dir="frames"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    cap = cv2.VideoCapture(video_path)
    count = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        if count % 30 == 0: # Save one frame per second
            cv2.imwrite(f"{output_dir}/frame_{count}.jpg", frame)
        count += 1
        if count > 150: break
    cap.release()
    print(f"Saved frames to {output_dir}")

if __name__ == "__main__":
    save_frames("/home/argjend/Desktop/Stake.com Bonus Drop Template (3).mp4")
