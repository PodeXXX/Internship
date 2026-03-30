import streamlit as st
import time
import pandas as pd
import json
import os
import uuid
from datetime import datetime
from hscode_brain import HSCodeBrain

# --- CẤU HÌNH FILE LƯU TRỮ ---
HISTORY_FILE = "chat_sessions.json"

# --- 1. CẤU HÌNH TRANG WEB ---
st.set_page_config(
    page_title="HS Code & Kho Hàng",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded" # <--- Quan trọng: Mặc định MỞ sidebar
)

# --- 2. CSS TÙY CHỈNH (FIX LỖI MẤT NÚT SIDEBAR) ---
st.markdown("""
<style>
    /* 1. Ẩn thanh trang trí cầu vồng và menu bên phải */
    [data-testid="stDecoration"] { display: none; }
    [data-testid="stToolbar"] { visibility: hidden; }
    
    /* 2. Header: Để nền trắng bình thường (không làm trong suốt nữa để tránh lỗi) */
    /* Chỉ ẩn border dưới chân */
    [data-testid="stHeader"] {
        background-color: white;
        border-bottom: none;
        height: 3.5rem; /* Thu nhỏ chiều cao header lại */
    }

    /* 3. BIỆN PHÁP MẠNH: GHIM CỨNG NÚT MỞ SIDEBAR */
    /* Dù header có bị gì thì nút này vẫn nổi ở góc trái */
    [data-testid="stSidebarCollapsedControl"] {
        position: fixed !important;
        top: 15px !important;
        left: 15px !important;
        display: block !important;
        visibility: visible !important;
        z-index: 999999 !important; /* Luôn nằm trên cùng */
        background-color: white !important;
        border: 1px solid #ddd !important;
        border-radius: 8px !important;
        padding: 2px !important;
        width: 40px !important;
        height: 40px !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        color: #31333F !important;
    }
    
    /* Hiệu ứng khi di chuột vào nút */
    [data-testid="stSidebarCollapsedControl"]:hover {
        background-color: #f0f2f6 !important;
        border-color: #31333F !important;
    }

    /* === STYLE GIAO DIỆN KHÁC === */
    .result-card {padding: 15px; border-radius: 8px; margin-bottom: 10px; font-size: 0.9rem; border: 1px solid #ddd;}
    .rule-box {background-color: #e8f5e9; border-color: #c8e6c9; color: #1b5e20;}
    .ai-box {background-color: #e3f2fd; border-color: #bbdefb; color: #0d47a1;}
    .not-found-box {background-color: #f5f5f5; color: #666; font-style: italic;}
    .stChatMessage { padding: 1rem; border-radius: 10px; }
    .color-alert {background-color: #fce4ec; color: #c2185b; padding: 15px; border-radius: 8px; border: 1px solid #f8bbd0; margin-bottom: 10px; font-size: 1rem;}
    .fabric-alert {background-color: #e8eaf6; color: #283593; padding: 15px; border-radius: 8px; border: 1px solid #c5cae9; margin-bottom: 10px; font-size: 1rem;}
    
    .welcome-container {text-align: center; padding: 50px 20px; background-color: #f8f9fa; border-radius: 15px; margin-top: 20px;}
    .welcome-title { font-size: 2.5em; font-weight: bold; color: #1E88E5; margin-bottom: 10px; }
    .welcome-subtitle { font-size: 1.2em; color: #555; margin-bottom: 30px; }
    .feature-card {background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); text-align: left; height: 100%;}
</style>
""", unsafe_allow_html=True)

# --- 3. HÀM QUẢN LÝ SESSION (LƯU TRỮ ĐA PHIÊN) ---
def load_all_sessions():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

def save_all_sessions(sessions):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=4)
    except Exception as e: print(f"Lỗi lưu file: {e}")

def create_new_session():
    session_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_sessions = load_all_sessions()
    all_sessions[session_id] = {
        "created_at": timestamp,
        "title": "Đoạn chat mới",
        "messages": []
    }
    save_all_sessions(all_sessions)
    return session_id

def update_current_session(session_id, messages, user_input=None):
    all_sessions = load_all_sessions()
    if session_id in all_sessions:
        all_sessions[session_id]["messages"] = messages
        if len(messages) == 2 and user_input:
            short_title = user_input[:30] + "..." if len(user_input) > 30 else user_input
            all_sessions[session_id]["title"] = short_title
        save_all_sessions(all_sessions)

# --- 4. KHỞI TẠO BỘ NÃO ---
@st.cache_resource
def load_brain_cached():
    brain = HSCodeBrain()
    def loading_callback(msg): print(msg) 
    brain.load_resources(loading_callback)
    while not brain.is_ready: time.sleep(0.5)
    return brain

try:
    brain = load_brain_cached()
except Exception as e:
    st.error(f"Lỗi khởi động hệ thống: {e}")
    st.stop()

# --- 5. KHỞI TẠO STATE BAN ĐẦU ---
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = create_new_session()

all_sessions_data = load_all_sessions()
curr_id = st.session_state.current_session_id

if curr_id in all_sessions_data:
    st.session_state.messages = all_sessions_data[curr_id]["messages"]
else:
    # Nếu id không tồn tại (do xóa file json chẳng hạn), tạo mới
    st.session_state.current_session_id = create_new_session()
    st.session_state.messages = []

# --- 6. SIDEBAR (QUẢN LÝ LỊCH SỬ) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2040/2040946.png", width=70)
    st.title("HS Chatbot")
    
    # Nút tạo chat mới (NÚT DẤU + MÀ BẠN CẦN)
    if st.button("➕ Đoạn chat mới", use_container_width=True, type="primary"):
        st.session_state.current_session_id = create_new_session()
        st.session_state.messages = []
        st.rerun()
    
    st.markdown("---")
    st.markdown("### 🕒 Lịch sử")
    
    sorted_sessions = sorted(
        all_sessions_data.items(), 
        key=lambda x: x[1].get("created_at", ""), 
        reverse=True
    )
    
    # Danh sách các đoạn chat cũ
    for s_id, s_data in sorted_sessions:
        title = s_data.get("title", "Không có tiêu đề")
        # Làm nổi bật session đang chọn
        prefix = "👉" if s_id == st.session_state.current_session_id else "💬"
        if st.button(f"{prefix} {title}", key=s_id, use_container_width=True):
            st.session_state.current_session_id = s_id
            st.rerun()

    st.markdown("---")
    if st.button("🗑️ Xóa TẤT CẢ dữ liệu", use_container_width=True):
        save_all_sessions({}) 
        st.session_state.current_session_id = create_new_session()
        st.rerun()
        
    st.caption("© 2024 Nhan Hoang Furniture")

# --- 7. HÀM HIỂN THỊ KẾT QUẢ ---
def display_response(data):
    search_mode = data.get('search_mode', 'hscode') 
    
    if search_mode == 'chitchat':
        st.info(data.get('message', 'Tôi không hiểu ý bạn.'))

    elif search_mode == 'fabric':
        fabric_data = data.get('fabric_data')
        if fabric_data and fabric_data['status'] == 'success':
            st.markdown(f"""
            <div class="fabric-alert">
                <strong>🧵 TÌM THẤY VẢI/NGUYÊN LIỆU</strong><br>
                Từ khóa: <strong>'{fabric_data['keyword']}'</strong>. 
                Tìm thấy <strong>{fabric_data['count']}</strong> mục.
            </div>
            """, unsafe_allow_html=True)
            with st.expander(f"📄 Nhấn để xem danh sách ({fabric_data['count']} mục)", expanded=False):
                df_fabric = pd.DataFrame(fabric_data['data'])
                st.dataframe(
                    df_fabric[['ProductCode', 'ProductName', 'SourceTable', 'MatInfo']],
                    column_config={"ProductCode": "Mã", "ProductName": "Tên SP", "SourceTable": "Nguồn", "MatInfo": "Thông tin Vải"},
                    use_container_width=True, hide_index=True, height=400
                )
        else:
            msg = fabric_data.get('message', 'Không tìm thấy dữ liệu vải.') if fabric_data else 'Lỗi tìm kiếm.'
            st.warning(msg)

    elif search_mode == 'color_only':
        color_data = data.get('color_data')
        st.markdown(f"""
        <div class="color-alert">
            <strong>🎨 TÌM THẤY TRONG KHO (MÀU SẮC)</strong><br>
            Màu: <strong>'{color_data['keyword']}'</strong>. 
            Tìm thấy <strong>{color_data['count']}</strong> sản phẩm.
        </div>
        """, unsafe_allow_html=True)
        with st.expander(f"📄 Nhấn để xem danh sách ({color_data['count']} sản phẩm)", expanded=False):
            df_colors = pd.DataFrame(color_data['products'])
            st.dataframe(
                df_colors[['Code', 'Name', 'ColorVIE']], 
                column_config={"Code": "Mã", "Name": "Tên SP", "ColorVIE": "Màu sắc"}, 
                use_container_width=True, hide_index=True, height=400
            )

    else: # HS CODE MODE
        rule_code = data.get('rule_code')
        ai_code = data.get('ai_code')
        ai_conf = data.get('ai_conf', 0)
        
        col1, col2 = st.columns(2)
        with col1:
            if rule_code:
                st.markdown(f"""<div class="result-card rule-box"><strong>🛡️ LUẬT:</strong> <span style="font-size: 1.3em; font-weight: bold;">{rule_code}</span><br><span style="font-size: 0.85em;">{data.get('rule_note','')}</span></div>""", unsafe_allow_html=True)
            else:
                st.markdown("""<div class="result-card not-found-box"><strong>🛡️ LUẬT:</strong> Không tìm thấy.</div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""<div class="result-card ai-box"><strong>🤖 AI Dự đoán:</strong> <span style="font-size: 1.3em; font-weight: bold;">{ai_code}</span><br><span style="font-size: 0.85em;">Độ tin cậy: {ai_conf:.1f}%</span></div>""", unsafe_allow_html=True)

        if data.get('color_data'):
            color_ref = data.get('color_data')
            st.info(f"💡 Phát hiện màu **'{color_ref['keyword']}'** ({color_ref['count']} sp). Bạn có thể tìm riêng màu này.")

        rec_text = data.get('recommendation', '')
        msg_type = data.get('msg_type', 'info')
        if msg_type == 'success': st.success(rec_text, icon="✅")
        elif msg_type == 'warning': st.warning(rec_text, icon="⚠️")
        elif msg_type == 'error': st.error(rec_text, icon="🛑")
        else: st.info(rec_text, icon="ℹ️")

    if 'steps' in data:
        with st.expander("🔍 Debug Log"):
            for step in data['steps']: st.code(step, language="text")

# --- 8. MÀN HÌNH CHÍNH ---
if not st.session_state.messages:
    st.markdown("""
    <div class="welcome-container">
        <div class="welcome-title">👋 Xin chào! Tôi là Trợ Lý Ảo</div>
        <div class="welcome-subtitle">Hỗ trợ tra cứu HS Code, Màu sắc và Vải.</div>
    </div>
    """, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown("""<div class="feature-card"><h4>🛡️ HS Code</h4><p>Nhập mô tả.</p><i>"Sofa khung gỗ"</i></div>""", unsafe_allow_html=True)
    with c2: st.markdown("""<div class="feature-card"><h4>🎨 Màu sắc</h4><p>Nhập tên màu.</p><i>"Green", "Sofa Green"</i></div>""", unsafe_allow_html=True)
    with c3: st.markdown("""<div class="feature-card"><h4>🧵 Vải / Liệu</h4><p>Nhập 'Vải' + tên.</p><i>"Vải Sunday 10"</i></div>""", unsafe_allow_html=True)
    st.write("") 

# --- 9. XỬ LÝ CHAT ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user": st.write(message["content"])
        else: display_response(message["content"])

if prompt := st.chat_input("Nhập mô tả, màu hoặc 'Vải + tên vải'..."):
    with st.chat_message("user"): st.write(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Lưu ngay tiêu đề nếu là tin nhắn đầu tiên
    update_current_session(st.session_state.current_session_id, st.session_state.messages, user_input=prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Đang xử lý..."):
            result = brain.analyze_product(prompt)
            # HS Code Logic
            if result.get('search_mode') == 'hscode':
                rule_code = result.get('rule_code')
                ai_code = result.get('ai_code')
                ai_conf = result.get('ai_conf', 0)
                rec_text, msg_type = "", "info"
                if rule_code and rule_code == ai_code: rec_text, msg_type = f"Tuyệt vời! Mã **{rule_code}** được xác nhận.", "success"
                elif rule_code and rule_code != ai_code: rec_text, msg_type = f"Xung đột: Luật **{rule_code}** - AI **{ai_code}**. Ưu tiên LUẬT.", "warning"
                else: 
                    if ai_conf > 85: rec_text, msg_type = f"AI tự tin dự đoán mã **{ai_code}** ({ai_conf:.1f}%).", "info"
                    else: rec_text, msg_type = "Cảnh báo: Độ tin cậy thấp.", "error"
                result['recommendation'] = rec_text
                result['msg_type'] = msg_type
            display_response(result)
            
    st.session_state.messages.append({"role": "assistant", "content": result})
    # Lưu tin nhắn bot
    update_current_session(st.session_state.current_session_id, st.session_state.messages)
    