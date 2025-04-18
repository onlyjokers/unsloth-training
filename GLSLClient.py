import zmq
import msgpack
import time
import threading
import uuid
import sys
import argparse
from pathlib import Path

class GLSLShaderClient:
    """GLSL Shader 测试客户端，发送GLSL代码组到服务器，接收编译结果"""
    def __init__(self, server_address="localhost", port=5566, timeout=15000, reverse_mode=False):
        self.server_address = server_address
        self.port = port
        self.timeout = timeout
        self.reverse_mode = reverse_mode
        self.context = zmq.Context()
        if reverse_mode:
            self.socket = self.context.socket(zmq.ROUTER)
            self.socket.setsockopt(zmq.RCVTIMEO, timeout)
        else:
            self.socket = self.context.socket(zmq.REQ)
            self.socket.setsockopt(zmq.RCVTIMEO, timeout)
            self.socket.setsockopt(zmq.SNDTIMEO, timeout)

    def connect(self):
        try:
            if self.reverse_mode:
                self.socket.bind(f"tcp://*:{self.port}")
                return True
            else:
                self.socket.connect(f"tcp://{self.server_address}:{self.port}")
                return True
        except zmq.ZMQError as e:
            print(f"连接服务器失败: {e}")
            return False

    def close(self):
        try:
            self.socket.close(linger=100)
        except:
            pass
        try:
            self.context.term()
        except:
            pass

    def send_shader_group(self, shader_group):
        # shader_group: list of dicts with 'name' and 'code'
        data = {
            'shader_group': shader_group
        }
        message = msgpack.packb(data)
        try:
            if self.reverse_mode:
                # 仅支持单一连接，简化实现
                print("反向模式暂未实现")
                return []
            else:
                self.socket.send(message)
                response_data = self.socket.recv()
                response = msgpack.unpackb(response_data, raw=False)
                return response
        except zmq.ZMQError as e:
            return [{
                'name': s.get('name'),
                'status': False,
                'error_msg': f"通信错误: {str(e)}",
                'accuracy_rank': 1,
                'meaning_rank': 1
            } for s in shader_group]

    def send_shader(self, shader_code, shader_name="remote_shader"):
        shader_group = [{
            'name': shader_name,
            'code': shader_code
        }]
        results = self.send_shader_group(shader_group)
        if results and len(results) > 0:
            return results[0]
        else:
            return {
                'name': shader_name,
                'status': False,
                'error_msg': '没有收到服务器响应',
                'accuracy_rank': 1,
                'meaning_rank': 1
            }

def send_shader_file(file_path, server_address="localhost", port=5566, reverse_mode=False):
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return {'name': str(file_path), 'status': False, 'error_msg': f"文件不存在: {file_path}", 'accuracy_rank': 1, 'meaning_rank': 1}
        with open(file_path, 'r', encoding='utf-8') as f:
            shader_code = f.read()
        shader_name = file_path.stem
        sender = GLSLShaderClient(server_address=server_address, port=port, reverse_mode=reverse_mode)
        if not sender.connect():
            return {'name': shader_name, 'status': False, 'error_msg': "无法连接到GLSL服务器", 'accuracy_rank': 1, 'meaning_rank': 1}
        response = sender.send_shader(shader_code, shader_name)
        sender.close()
        return response
    except Exception as e:
        return {'name': str(file_path), 'status': False, 'error_msg': f"发送shader时出错: {str(e)}", 'accuracy_rank': 1, 'meaning_rank': 1}

def send_shaders_json(shader_json, server_address="localhost", port=5566, reverse_mode=False, timeout=15000):
    try:
        if not isinstance(shader_json, list):
            return [{'name': '输入', 'status': False, 'error_msg': "输入格式错误：应提供shader对象列表", 'accuracy_rank': 1, 'meaning_rank': 1}]
        shader_group = []
        for idx, shader in enumerate(shader_json):
            if not isinstance(shader, dict) or "name" not in shader or "code" not in shader:
                return [{'name': f'shader_{idx+1}', 'status': False, 'error_msg': f"shader #{idx+1} 格式错误：缺少name或code字段", 'accuracy_rank': 1, 'meaning_rank': 1}]
            shader_group.append({
                'name': shader["name"],
                'code': shader["code"]
            })
        sender = GLSLShaderClient(server_address=server_address, port=port, reverse_mode=reverse_mode, timeout=timeout)
        if not sender.connect():
            return [{'name': s['name'], 'status': False, 'error_msg': "无法连接到GLSL服务器", 'accuracy_rank': 1, 'meaning_rank': 1} for s in shader_group]
        results = sender.send_shader_group(shader_group)
        sender.close()
        return results
    except Exception as e:
        return [{'name': '批量', 'status': False, 'error_msg': f"发送shader时出错: {str(e)}", 'accuracy_rank': 1, 'meaning_rank': 1}]

def main():
    parser = argparse.ArgumentParser(description="发送GLSL shader文件到服务器")
    parser.add_argument('file', help="GLSL shader代码文件路径")
    parser.add_argument('-s', '--server', default="localhost", help="GLSL服务器地址")
    parser.add_argument('-p', '--port', type=int, default=5566, help="服务器端口/客户端监听端口")
    parser.add_argument('-r', '--reverse', action='store_true', help="使用反向连接模式")
    parser.add_argument('-t', '--timeout', type=int, default=15000, help="超时时间(毫秒)，默认15000")
    args = parser.parse_args()
    response = send_shader_file(args.file, args.server, args.port, args.reverse)
    print(f"Shader: {response.get('name', '未知')}")
    print(f"状态: {response.get('status', '未知')}")
    if response.get('error_msg'):
        print(f"错误信息: {response['error_msg']}")
    print(f"accuracy_rank: {response.get('accuracy_rank', 1)}")
    print(f"meaning_rank: {response.get('meaning_rank', 1)}")
    if response.get('status') != True:
        sys.exit(1)

if __name__ == "__main__":
    main()
