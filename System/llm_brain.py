import json
from google import genai
from google.genai import types
from pydantic import BaseModel

# ==========================================
# CẤU HÌNH API KEY
# ==========================================
GOOGLE_API_KEY = "AIzaSyAR-fqkphJX_DAM4zi41nBzGfLpN3wi5u0" 

# ÉP BUỘC KHUÔN MẪU JSON ĐẦU RA 
# AI bắt buộc phải đẻ ra đúng 3 trường này, không được chế thêm
class AIResponse(BaseModel):
    status: str
    search_mode: str
    message: str

class LLMBrain:
    def __init__(self):
        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        
        self.system_prompt = """
        Bạn là một Trợ Lý Ảo AI chuyên nghiệp, tên là "Trợ Lý ERP Nhân Hoàng". Bạn làm việc tại hệ thống kho hàng và nội thất của công ty Nhân Hoàng.
        
        QUY TẮC BẮT BUỘC:
        1. Luôn trả lời bằng tiếng Việt thân thiện. Sử dụng các thẻ HTML cơ bản (<b>, <br>, <ul>, <li>) để trang trí cho văn bản hiển thị đẹp mắt.
        2. Nếu được yêu cầu trích xuất thông tin, hãy bóc tách chính xác và trình bày thành danh sách (bullet points) gọn gàng trong phần 'message'.
        3. Nếu người dùng chitchat: Hãy giới thiệu bạn hỗ trợ tra mã HS Code, tính CBM, tra BOM và tồn kho.
        4. Khước từ khéo léo mọi chủ đề không liên quan đến kho hàng, ERP, nội thất.
        """

    def process_chat(self, user_input):
        try:
            full_prompt = f"{self.system_prompt}\n\n[Câu hỏi của người dùng]: {user_input}"
            
            # Gửi request lên server Google và ÉP KHUÔN SCHEMA
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AIResponse, # <--- Trói chặt cấu trúc tại đây
                )
            )
            
            # Đọc kết quả
            result = json.loads(response.text)
            
            # Ép cứng giá trị để giao diện Web không bao giờ bị lỗi toFixed nữa
            result["search_mode"] = "chitchat"
            result["status"] = "ok"
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            print(f"🚨 [LLM_BRAIN] LỖI: {error_msg}")
            return {
                "status": "error",
                "search_mode": "chitchat",
                "message": f"🤖 <b>AI gặp sự cố:</b> <br><small><i>({error_msg})</i></small>"
            }

if __name__ == "__main__":
    brain = LLMBrain()
    print(brain.process_chat("Hãy trích xuất mã sản phẩm 50002584 màu dark green"))