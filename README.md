📌 Face Recognition Based Online Voting System

🧠 Project Overview

This project is a secure online voting system that uses face recognition technology to authenticate users and prevent duplicate or fraudulent voting. It ensures that only verified users can cast their vote, making the voting process more reliable and tamper-proof.

🚀 Features

🔐 User authentication using User ID & Password
👤 Face Recognition Verification for secure login
🗳️ One user can vote only once
📊 Admin panel to manage candidates and positions
📁 Export voting results in CSV format
🖼️ Image upload & webcam capture for face registration

🛠️ Tech Stack

Frontend: HTML, CSS, JavaScript
Backend: Flask (Python)
Database: SQLite
Libraries: OpenCV, face_recognition, NumPy
Authentication: Face Encoding + Password Hashing

⚙️ How It Works

User Registration
User registers with name, user ID, password, and face image
Face encoding is generated and stored in the database
Login & Verification
User logs in with credentials
Face is verified using stored encoding
Access granted only if face matches
Voting Process
User selects a candidate
System checks if the user has already voted
Vote is securely recorded in the database
Admin Control
Add/manage candidates and positions
View results and export data
