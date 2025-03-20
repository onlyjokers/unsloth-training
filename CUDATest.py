import torch
import triton
import xformers
import unsloth

# 尝试一个简单的 GPU 操作
if torch.cuda.is_available():
    print("============== 环境信息 ==============")
    print(f"PyTorch 版本: {torch.__version__}")
    print(f"CUDA 可用: {torch.cuda.is_available()}")
    print(f"当前 CUDA 设备: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else '无'}")
    print(f"Triton 版本: {triton.__version__ if hasattr(triton, '__version__') else '已安装'}")
    print(f"xformers 版本: {xformers.__version__ if hasattr(xformers, '__version__') else '已安装'}")
    print(f"Unsloth 版本: {unsloth.__version__ if hasattr(unsloth, '__version__') else '已安装'}")
    print("============== GPU 测试 ==============")
    tensor = torch.tensor([1.0, 2.0, 3.0]).cuda()
    print(f"GPU 张量: {tensor}")