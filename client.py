"""
材质数据发送客户端

该模块用于从电脑1发送材质数据到运行Blender的电脑2
支持反向连接模式：服务端主动连接到公网客户端
支持发送材质组：可以一次性发送多个材质
"""

import zmq
import msgpack
import time
import os
import argparse
import json
from pathlib import Path
import sys
import threading
import uuid
import queue

class MaterialSender:
    """材质数据发送器，使用ZeroMQ发送材质数据到Blender服务器
    
    支持两种模式：
    1. 传统模式：客户端主动连接服务器（REQ-REP）
    2. 反向连接：服务器主动连接客户端（DEALER-ROUTER）
    """
    
    def __init__(self, server_address="localhost", port=5555, timeout=15000, reverse_mode=False):
        """初始化ZeroMQ客户端
        
        Args:
            server_address: 服务器地址，默认localhost
            port: 服务器端口或客户端监听端口，默认5555
            timeout: 连接和发送超时时间(毫秒)，默认15000(15秒)
            reverse_mode: 是否使用反向连接模式，默认False
        """
        self.server_address = server_address
        self.port = port
        self.timeout = timeout
        self.reverse_mode = reverse_mode
        self.context = zmq.Context()
        
        # 初始化会话ID，用于反向模式下消息匹配
        self.session_id = str(uuid.uuid4())[:8]
        
        if reverse_mode:
            # 反向连接模式：客户端作为ROUTER，等待服务器连接
            self.socket = self.context.socket(zmq.ROUTER)
            self.socket.setsockopt(zmq.RCVTIMEO, timeout)
            # 连接管理
            self.clients = {}  # 存储连接的服务端ID
            self.connected_event = threading.Event()
            
            # 消息队列，用于不同线程间传递消息
            self.message_queue = queue.Queue()
            self.response_event = threading.Event()
            
            # 启动监听线程
            self.running = True
            self.listener_thread = threading.Thread(target=self._connection_listener)
            self.listener_thread.daemon = True
        else:
            # 传统模式：客户端作为REQ，主动连接服务器
            self.socket = self.context.socket(zmq.REQ)
            self.socket.setsockopt(zmq.RCVTIMEO, timeout)
            self.socket.setsockopt(zmq.SNDTIMEO, timeout)
    
    def connect(self):
        """连接到服务器或启动监听"""
        try:
            if self.reverse_mode:
                # 反向模式：绑定到端口，等待服务器连接
                print(f"使用反向连接模式，在端口 {self.port} 上监听服务器连接...")
                self.socket.bind(f"tcp://*:{self.port}")
                self.listener_thread.start()
                # 等待连接建立，最多等待30秒
                if not self.connected_event.wait(30):
                    print("警告：尚未有服务器连接，但将继续等待连接...")
                return True
            else:
                # 传统模式：主动连接到服务器
                print(f"连接到服务器 {self.server_address}:{self.port}...")
                self.socket.connect(f"tcp://{self.server_address}:{self.port}")
                return True
        except zmq.ZMQError as e:
            print(f"连接服务器失败: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if hasattr(self, 'running'):
            self.running = False
        if hasattr(self, 'listener_thread') and self.listener_thread.is_alive():
            self.listener_thread.join(1.0)
        
        # 确保安全关闭
        time.sleep(0.5)
        
        if hasattr(self, 'socket'):
            try:
                self.socket.close(linger=100)  # 设置延迟关闭时间
            except:
                pass
        if hasattr(self, 'context'):
            try:
                self.context.term()
            except:
                pass
        print("客户端已关闭")
    
    def _connection_listener(self):
        """监听连接的线程（仅反向模式使用）"""
        print("启动连接监听线程...")
        
        while self.running:
            try:
                # 尝试接收任何消息，但不阻塞太长时间，以便可以检查running标志
                if not self.socket.poll(timeout=500, flags=zmq.POLLIN):
                    continue
                
                parts = self.socket.recv_multipart()
                if len(parts) < 3:
                    print(f"收到格式错误的消息，包含 {len(parts)} 个部分")
                    continue
                    
                server_id, empty, msg = parts
                
                # 记录新连接的服务端
                if server_id not in self.clients:
                    self.clients[server_id] = time.time()
                    print(f"服务器已连接 (ID: {server_id.hex()[:8]})")
                    self.connected_event.set()
                
                # 如果是心跳消息，回应心跳
                if msg == b'PING':
                    print(f"收到服务器心跳，发送PONG回应...")
                    self.socket.send_multipart([server_id, b'', b'PONG'])
                else:
                    # 解析响应消息，检查是否包含材质结果
                    try:
                        response = msgpack.unpackb(msg, raw=False)
                        if 'material_results' in response:
                            print(f"收到材质处理响应: {len(response['material_results'])} 个结果")
                            # 放入队列供主线程处理
                            self.message_queue.put((server_id, response))
                            # 设置响应事件，通知主线程
                            self.response_event.set()
                        elif 'status' in response:
                            print(f"收到状态响应: {response['status']}")
                            # 放入队列供主线程处理
                            self.message_queue.put((server_id, response))
                            # 设置响应事件，通知主线程
                            self.response_event.set()
                        else:
                            print(f"收到未知响应格式: {response.keys()}")
                    except Exception as e:
                        print(f"解析响应消息失败: {e}")
                        import traceback
                        traceback.print_exc()
                
            except zmq.ZMQError as e:
                if str(e) != "Resource temporarily unavailable":  # 忽略常规超时
                    print(f"ZMQ监听错误: {e}")
            except Exception as e:
                import traceback
                print(f"监听线程错误: {e}")
                traceback.print_exc()
                time.sleep(1)  # 避免错误循环过快
    
    def send_material_group(self, material_group):
        """发送材质组数据到服务器
        
        Args:
            material_group: 材质组列表，每个元素应包含id, name, code
            
        Returns:
            list: 包含处理结果的列表
        """
        # 准备发送的数据
        data = {
            'material_group': material_group,
            'session_id': self.session_id,
            'timestamp': time.time()
        }
        
        # 打包数据
        message = msgpack.packb(data)
        
        try:
            if self.reverse_mode:
                # 反向模式：等待至少一个服务器连接
                if not self.clients:
                    print("等待服务器连接...")
                    if not self.connected_event.wait(10.0):
                        return [{
                            'id': m.get('id'),
                            'name': m.get('name'),
                            'status': False,
                            'error_msg': "没有服务器连接",
                            'rank': idx + 1
                        } for idx, m in enumerate(material_group)]
                
                # 反向模式：向所有连接的服务器发送
                material_names = [m.get('name', f"材质{m.get('id', 'unknown')}") for m in material_group]
                print(f"正在发送材质组 ({len(material_group)}个材质) 到已连接的服务器")
                
                # 获取第一个可用的服务器ID
                server_id = list(self.clients.keys())[0]
                
                # 重置响应事件
                self.response_event.clear()
                
                # 清空可能存在的旧消息
                while not self.message_queue.empty():
                    try:
                        self.message_queue.get_nowait()
                    except queue.Empty:
                        break
                
                # 发送多部分消息：[服务器ID, 空帧, 实际数据]
                print(f"向服务器 {server_id.hex()[:8]} 发送 {len(material_group)} 个材质...")
                self.socket.send_multipart([server_id, b'', message])
                
                # 等待响应 - 使用事件和消息队列
                response_timeout = self.timeout / 1000.0  # 转换为秒
                print(f"等待服务器响应，超时时间 {response_timeout} 秒...")
                
                # 等待响应事件
                if not self.response_event.wait(response_timeout):
                    print("等待服务器响应超时!")
                    return [{
                        'id': m.get('id'),
                        'name': m.get('name'),
                        'status': False,
                        'error_msg': "服务器响应超时",
                        'rank': idx + 1
                    } for idx, m in enumerate(material_group)]
                
                try:
                    # 从消息队列获取响应
                    recv_server_id, response = self.message_queue.get(block=False)
                    
                    # 验证消息是否来自预期的服务器
                    if recv_server_id == server_id:
                        print(f"收到来自服务器 {server_id.hex()[:8]} 的有效响应")
                        # 输出完整响应进行调试
                        if 'material_results' in response:
                            material_results = response.get('material_results', [])
                            print(f"响应包含 {len(material_results)} 个材质结果")
                            return material_results
                        else:
                            print("警告：服务器响应中没有'material_results'字段")
                            print(f"收到的响应键: {list(response.keys())}")
                            # 尝试使用向后兼容的方式处理旧格式响应
                            if 'status' in response:
                                status = response.get('status', 'failed')
                                error_msg = response.get('error_msg', '未知错误')
                                return [{
                                    'id': 1,
                                    'name': '未知材质',
                                    'status': status == 'Success',
                                    'error_msg': error_msg,
                                    'rank': 1
                                }]
                    else:
                        print(f"收到来自未预期服务器的响应: {recv_server_id.hex()[:8]}")
                        
                except queue.Empty:
                    print("警告：响应事件被触发但队列为空")
                    
                # 如果到这里还没有返回，说明出现了问题
                print("处理响应时遇到问题，返回空结果")
                return []
                
            else:
                # 传统模式：直接发送到服务器
                material_names = [m.get('name', f"材质{m.get('id', 'unknown')}") for m in material_group]
                print(f"正在发送材质组 ({len(material_group)}个材质) 到 {self.server_address}:{self.port}")
                self.socket.send(message)
                
                # 等待响应
                print("等待服务器响应...")
                response_data = self.socket.recv()
                response = msgpack.unpackb(response_data, raw=False)
                
                return response.get('material_results', [])
                
        except zmq.ZMQError as e:
            print(f"发送材质数据失败: {e}")
            return [{
                'id': m.get('id'),
                'name': m.get('name'),
                'status': False,
                'error_msg': f"通信错误: {str(e)}",
                'rank': idx + 1
            } for idx, m in enumerate(material_group)]
    
    def send_material(self, material_code, material_name="remote_material"):
        """发送单个材质数据到服务器 (向下兼容)
        
        Args:
            material_code: 材质的Python代码
            material_name: 材质名称
            
        Returns:
            dict: 包含status和error_msg的响应字典
        """
        # 将单个材质封装为材质组格式
        material_group = [{
            'id': 1,
            'name': material_name,
            'code': material_code
        }]
        
        # 发送材质组并获取结果
        results = self.send_material_group(material_group)
        
        # 从结果列表中提取单个材质的结果
        if results and len(results) > 0:
            result = results[0]
            return {
                'status': 'Success' if result.get('status') else 'failed',
                'error_msg': result.get('error_msg', '')
            }
        else:
            return {
                'status': 'failed',
                'error_msg': '没有收到服务器响应'
            }

def send_text_to_blender(material_code, material_name="remote_material_from_text", server_address="localhost", port=5555, reverse_mode=False, timeout=15000):
    """直接发送文本形式的材质代码到Blender服务器
    
    Args:
        material_code: 材质的Python代码字符串
        material_name: 材质名称 (可选)
        server_address: 服务器地址
        port: 服务器端口
        reverse_mode: 是否使用反向连接模式
        timeout: 超时时间(毫秒)
        
    Returns:
        dict: 包含状态和错误信息的响应
    """
    try:
        # 创建发送器
        sender = MaterialSender(server_address=server_address, port=port, reverse_mode=reverse_mode, timeout=timeout)
        if not sender.connect():
            return {'status': 'failed', 'error_msg': "无法连接到Blender服务器"}
        
        # 发送材质 (使用内部的 send_material 方法)
        response = sender.send_material(material_code, material_name)
        sender.close()
        
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'status': 'failed', 'error_msg': f"发送材质文本时出错: {str(e)}"}

def send_file_to_blender(file_path, server_address="localhost", port=5555, reverse_mode=False):
    """发送材质文件到Blender服务器
    
    Args:
        file_path: 材质文件路径
        server_address: 服务器地址
        port: 服务器端口
        reverse_mode: 是否使用反向连接模式
        
    Returns:
        dict: 包含状态和错误信息的响应
    """
    # 读取文件
    try:
        file_path = Path(file_path)
        if not file_path.exists():
            return {'status': 'failed', 'error_msg': f"文件不存在: {file_path}"}
        
        # 读取材质代码
        with open(file_path, 'r', encoding='utf-8') as f:
            material_code = f.read()
        
        # 从文件名获取材质名称
        material_name = file_path.stem
        
        # 创建发送器
        sender = MaterialSender(server_address=server_address, port=port, reverse_mode=reverse_mode)
        if not sender.connect():
            return {'status': 'failed', 'error_msg': "无法连接到Blender服务器"}
        
        # 发送材质
        response = sender.send_material(material_code, material_name)
        sender.close()
        
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'status': 'failed', 'error_msg': f"发送材质时出错: {str(e)}"}

def main():
    """命令行入口点"""
    parser = argparse.ArgumentParser(description="发送材质文件到Blender")
    parser.add_argument('file', help="材质Python代码文件路径")
    parser.add_argument('-s', '--server', default="localhost", help="Blender服务器地址")
    parser.add_argument('-p', '--port', type=int, default=5555, help="服务器端口/客户端监听端口")
    parser.add_argument('-r', '--reverse', action='store_true', help="使用反向连接模式")
    parser.add_argument('-t', '--timeout', type=int, default=15000, help="超时时间(毫秒)，默认15000")
    
    args = parser.parse_args()
    
    # 发送文件
    response = send_file_to_blender(args.file, args.server, args.port, args.reverse)
    
    # 打印结果
    print(f"状态: {response.get('status', '未知')}")
    if response.get('error_msg'):
        print(f"错误信息: {response['error_msg']}")
    
    # 设置退出码
    if response.get('status') != 'Success':
        sys.exit(1)

if __name__ == "__main__":
    main()