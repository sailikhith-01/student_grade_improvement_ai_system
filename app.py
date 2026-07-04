import streamlit as st
import sqlite3
import pandas as pd
import base64
import time
import requests


'''
user name: likhith
password: password
'''
# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Student Grade Improvement System", 
    page_icon="🎓", 
    layout="centered"
)

# ==========================================
# ### USER CONFIGURATION ###
# ==========================================
BACKGROUND_IMAGE_FILENAME = 'background.png' 

# Fetch API Keys securely from Streamlit Secrets
try:
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
except KeyError:
    YOUTUBE_API_KEY = None

try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
except KeyError:
    OPENROUTER_API_KEY = None
# ==========================================


# --- DATABASE FUNCTIONS ---
def init_db():
    conn = sqlite3.connect('student_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS student_marks 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  cgpa REAL, 
                  semester_details TEXT)''')
    try:
        c.execute("INSERT INTO users (username, password) VALUES ('admin', '1234')")
        conn.commit()
    except sqlite3.IntegrityError:
        pass 
    conn.close()

def create_user(username, password):
    conn = sqlite3.connect('student_data.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False 
    finally:
        conn.close()

def check_login(username, password):
    conn = sqlite3.connect('student_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = c.fetchone()
    conn.close()
    return user

def save_data(username, cgpa, details):
    conn = sqlite3.connect('student_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO student_marks (username, cgpa, semester_details) VALUES (?, ?, ?)", 
              (username, cgpa, str(details)))
    conn.commit()
    conn.close()


# --- LLM ANALYSIS LOGIC (OPENROUTER) ---
def analyze_student_performance(cgpa, subject_data, exam_type):
    """Uses OpenRouter to generate personalized suggestions."""
    
    # Overall Performance Category
    if cgpa == 10.0:
        category = "Excellent"
    elif 9.0 <= cgpa < 10.0:
        category = "Good"
    elif 6.0 <= cgpa < 9.0:
        category = "Average"
    else:
        category = "Below Average"

    if not OPENROUTER_API_KEY:
        return category, ["⚠️ **API Key Missing:** Please add your OPENROUTER_API_KEY to your secrets.toml file."]

    # Format data so the AI sees the marks, the calculated grade, and the exam type
    grades_summary = ", ".join([f"{item['Subject']} (Marks: {item['Marks']}/50, Grade: {item['Grade']})" for item in subject_data])

    # 1. Base instructions
    base_prompt = (
        f"You are an expert university academic counselor. "
        f"The student just completed their {exam_type} internal exams. "
        f"Their overall historical CGPA is {cgpa}. "
        f"In these recent exams (out of 50 marks per subject), they scored: {grades_summary}. "
        f"Base your advice heavily on BOTH their overall CGPA and how they performed in these specific subjects. "
        f"Keep the tone encouraging and professional. "
    )

    # 2. Dynamic instructions based on CGPA category
    if cgpa == 10.0:
        prompt = base_prompt + (
            "Because they have a perfect historical score, focus your advice on maintaining this for finals, and shifting focus to career growth. "
            "Encourage them to build advanced personal projects, attend competitive hackathons, and apply for top-tier internships. "
            "Format the response strictly as a bulleted list. Do NOT generate a study timetable."
        )
        
    elif 6.0 <= cgpa < 10.0:
        prompt = base_prompt + (
            "Provide highly specific, actionable tips to help them improve their current exam marks and push for the next CGPA tier. "
            "Address specific subjects where they scored poorly (below 40). "
            "Additionally, you MUST create a customized daily evening study timetable spanning exactly from 7:00 PM to 12:00 AM. "
            "Schedule their weakest subjects for the most study time. "
            "You must include exactly one 30-minute break for 'Dinner & Relaxation' scheduled between 7:00 PM and 8:30 PM. "
            "Format your response strictly as: first, a bulleted list of 3-4 tips, followed by a clean Markdown table for the study schedule."
        )
        
    else:
        prompt = base_prompt + (
            "Provide highly specific, structured tips to help them focus, recover from poor exam marks, and rebuild their foundation. "
            "Additionally, you MUST create a rigorous daily evening study timetable spanning exactly from 7:00 PM to 12:00 AM. "
            "Allocate the majority of the time to their lowest-graded subjects. "
            "You must include exactly one 30-minute break for 'Dinner & Relaxation' scheduled between 7:00 PM and 8:30 PM. "
            "Format your response strictly as: first, a bulleted list of 3-4 tips, followed by a clean Markdown table for the study schedule."
        )

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "tencent/hy3-preview:free",   #inclusionai/ling-2.6-1t:free
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        
        data = response.json()
        
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown API Error")
            return category, [f"⚠️ **OpenRouter Refused Request:** {error_msg}"]

        ai_message = data['choices'][0]['message']['content']
        suggestions = [line.strip() for line in ai_message.split('\n') if line.strip()]
        return category, suggestions

    except Exception as e:
        return category, [f"⚠️ **System Error:** {str(e)}"]


# --- DYNAMIC COURSE RECOMMENDATION (YOUTUBE) ---
def get_dynamic_course_link(subject_name):
    """Uses YouTube API to find the best academic lecture for any subject."""
    fallback_url = f"https://www.youtube.com/results?search_query={subject_name.replace(' ', '+')}+university+course"
    
    if not YOUTUBE_API_KEY:
        return fallback_url, f"Search YouTube for {subject_name}"

    search_url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        'part': 'snippet',
        'q': f"{subject_name} university engineering course NPTEL", 
        'type': 'playlist,video',
        'maxResults': 1,
        'key': YOUTUBE_API_KEY
    }

    try:
        response = requests.get(search_url, params=params)
        data = response.json()
        if 'items' in data and len(data['items']) > 0:
            item = data['items'][0]
            title = item['snippet']['title']
            if 'playlistId' in item['id']:
                link = f"https://www.youtube.com/playlist?list={item['id']['playlistId']}"
            else:
                link = f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                
            short_title = (title[:35] + '...') if len(title) > 35 else title
            return link, f"▶️ Watch: {short_title}"
    except Exception as e:
        pass 

    return fallback_url, f"Search YouTube for {subject_name}"


# --- STYLING & BACKGROUND ---
def get_base64(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def set_background(png_file):
    try:
        bin_str = get_base64(png_file)
        page_bg_img = f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{bin_str}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        .stForm, .stContainer, div[data-testid="stVerticalBlock"] > div {{
            background-color: rgba(255, 255, 255, 0.92);
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        h1 {{
            color: #1A365D; 
            background-color: rgba(255, 255, 255, 0.92);
            text-align: center;
            font-size: 2.5rem;
            padding: 20px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            font-weight: 800;
        }}
        </style>
        """
        st.markdown(page_bg_img, unsafe_allow_html=True)
    except FileNotFoundError:
        pass


# --- PAGE 1: LOGIN & REGISTRATION ---
def login_page():
    st.markdown("<h1>Student Grade Improvement<br>Recommendation System</h1>", unsafe_allow_html=True)
    
    if 'auth_mode' not in st.session_state:
        st.session_state['auth_mode'] = 'login'

    with st.container():
        if st.session_state['auth_mode'] == 'login':
            st.subheader("🔐 Login")
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Login", type="primary", use_container_width=True):
                    if check_login(username, password):
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = username
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password")
            
            with col2:
                if st.button("Create Account", use_container_width=True):
                    st.session_state['auth_mode'] = 'signup'
                    st.rerun()

        else:
            st.subheader("📝 New User Registration")
            new_user = st.text_input("Choose a Username", key="new_user")
            new_pass = st.text_input("Choose a Password", type="password", key="new_pass")
            confirm_pass = st.text_input("Confirm Password", type="password", key="conf_pass")
            
            if st.button("Register", type="primary", use_container_width=True):
                if new_pass != confirm_pass:
                    st.error("Passwords do not match!")
                elif new_user == "":
                    st.error("Username cannot be empty.")
                else:
                    if create_user(new_user, new_pass):
                        st.success("Account created successfully! Please log in.")
                        time.sleep(1.5)
                        st.session_state['auth_mode'] = 'login'
                        st.rerun()
                    else:
                        st.error("Username already exists. Please choose another.")
            
            if st.button("Back to Login"):
                st.session_state['auth_mode'] = 'login'
                st.rerun()


# --- PAGE 2: DATA ENTRY & RECOMMENDATIONS ---
def data_entry_page():
    st.markdown(f"<h1>Welcome, {st.session_state['username']}</h1>", unsafe_allow_html=True)
    
    col_head1, col_head2 = st.columns([4, 1])
    with col_head2:
        if st.button("Logout"):
            st.session_state['logged_in'] = False
            st.rerun()

    with st.container():
        st.write("Please enter your details below to get personalized AI recommendations.")
        
        col1, col2 = st.columns(2)
        with col1:
            cgpa = st.number_input("Overall Historical CGPA", min_value=0.0, max_value=10.0, step=0.01)
        with col2:
            num_subjects = st.number_input("No. of Subjects in Exam", min_value=1, max_value=15, step=1, value=1)

    st.write("") 

    with st.form("marks_form"):
        st.subheader("Exam Performance Entry")
        
        # --- NEW: EXAM TYPE DROPDOWN ---
        exam_type = st.selectbox("Exam Type", options=["CAT1", "CAT2"])
        
        
        subject_data = []
        
        for i in range(int(num_subjects)):
            st.markdown(f"**Subject {i+1}**")
            
            # --- NEW: ONLY TWO COLUMNS NOW (NAME AND MARKS) ---
            c1, c2 = st.columns([3, 1])
            with c1:
                sub_name = st.text_input(f"Subject Name", key=f"sub_{i}", placeholder="e.g. Data Structures")
            with c2:
                # Max marks updated to 50
                sub_mark = st.number_input(f"Marks (Max 50)", min_value=0, max_value=50, key=f"mark_{i}")
            
            # --- NEW: DYNAMIC GRADE CALCULATION ---
            if sub_mark > 45:
                calc_grade = "A"
            elif 40 < sub_mark <= 45:
                calc_grade = "B"
            elif 35 < sub_mark <= 40:
                calc_grade = "C"
            elif 30 < sub_mark <= 35:
                calc_grade = "D"
            elif 25 < sub_mark <= 30:
                calc_grade = "E"
            else:
                calc_grade = "F"
                
            st.caption(f"*Calculated Grade: {calc_grade}*")
            
            # Save the calculated grade into the data list
            subject_data.append({
                "Exam": exam_type, 
                "Subject": sub_name, 
                "Marks": sub_mark, 
                "Grade": calc_grade
            })
            
            
        submitted = st.form_submit_button("Submit & Analyze Performance", type="primary")
        
        if submitted:
            if any(d['Subject'] == "" for d in subject_data):
                st.error("❌ Please ensure all Subject Names are filled in.")
            else:
                save_data(st.session_state['username'], cgpa, subject_data)
                
                # Pass the exam type to the AI function
                with st.spinner("🤖 AI is analyzing your performance and creating a timetable..."):
                    category, suggestions = analyze_student_performance(cgpa, subject_data, exam_type)
                
                st.subheader("📊 AI Performance Analysis")
                
                if category == "Excellent":
                    st.success(f"**Overall Classification: {category}**")
                elif category == "Good":
                    st.info(f"**Overall Classification: {category}**")
                elif category == "Average":
                    st.warning(f"**Overall Classification: {category}**")
                else:
                    st.error(f"**Overall Classification: {category}**")
                
                with st.expander("💡 Click here to view your AI Actionable Tips & Timetable", expanded=True):
                    for tip in suggestions:
                        st.markdown(tip) 
                
                st.write("### Submitted Data Summary")
                st.dataframe(pd.DataFrame(subject_data), use_container_width=True)

                # --- SMART COURSE REDIRECTS ---
                st.subheader("🔗 Recommended Online Courses")
                st.write("Based on your marks, we recommend brushing up on these specific subjects:")
                
                needs_help = False
                for course in subject_data:
                    # Trigger YouTube recommendation if grade is B or lower
                    if course['Grade'] in ['B', 'C', 'D', 'E', 'F']:
                        needs_help = True
                        url, platform_name = get_dynamic_course_link(course['Subject'])
                        
                        colA, colB = st.columns([3, 1])
                        with colA:
                            st.error(f"**{course['Subject']}** (Marks: {course['Marks']}/50 | Grade: {course['Grade']})")
                        with colB:
                            st.link_button(f"{platform_name}", url)
                
                if not needs_help:
                    st.success("Outstanding job! You scored 'A's across the board. No remedial courses needed.")

# --- MAIN APP LOGIC ---
def main():
    init_db()
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    set_background(BACKGROUND_IMAGE_FILENAME)

    if not st.session_state['logged_in']:
        login_page()
    else:
        data_entry_page()

if __name__ == "__main__":
    main()