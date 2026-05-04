import os
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer
from app.core.config import settings

def optimize():
    model_id = settings.MODEL_NAME
    onnx_path = "./models_onnx"
    
    print(f"🚀 Memulai optimasi model: {model_id}")
    
    if not os.path.exists(onnx_path):
        os.makedirs(onnx_path)
        
    # Load and export to ONNX
    # ORTModelForFeatureExtraction akan otomatis mendownload dan melakukan konversi
    print("📦 Mendownload dan mengekspor model ke format ONNX...")
    model = ORTModelForFeatureExtraction.from_pretrained(model_id, export=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    # Simpan model ONNX secara lokal
    model.save_pretrained(onnx_path)
    tokenizer.save_pretrained(onnx_path)
    
    print(f"✅ Model berhasil dioptimasi dan disimpan di: {onnx_path}")
    print("💡 Anda sekarang bisa mengubah EmbeddingService untuk menggunakan model ini.")

if __name__ == "__main__":
    optimize()
