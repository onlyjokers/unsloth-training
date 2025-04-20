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
            material_group: 可以是列表或包含outputs字段的dict
            
        Returns:
            list: 包含处理结果的列表
        """
        # 准备发送的数据，支持 dict 或 list
        if isinstance(material_group, dict):
            data = material_group.copy()
            # 新版格式中的材质列表
            material_list = data.get('outputs', data.get('material_group', []))
        else:
            material_list = material_group
            data = {
                'material_group': material_list,
                'session_id': self.session_id,
                'timestamp': time.time()
            }
         
        # 打包数据
        message = msgpack.packb(data)
        
        # 添加重试逻辑
        max_retries = 5
        retry_delay = 1  # 秒
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                if self.reverse_mode:
                    # 反向模式：等待至少一个服务器连接
                    if not self.clients:
                        print("等待服务器连接...")
                        if not self.connected_event.wait(10.0):
                            # 无服务器连接，尝试重试
                            retry_count += 1
                            if retry_count < max_retries:
                                print(f"没有服务器连接，第 {retry_count}/{max_retries} 次尝试重新等待...")
                                time.sleep(retry_delay)
                                continue
                            else:
                                # 达到最大重试次数，全部返回失败
                                return [{
                                    'id': m.get('id'),
                                    'name': m.get('name'),
                                    'status': False,
                                    'error_msg': "多次尝试后仍无服务器连接",
                                    'accuracy_rank': 0,
                                    'meaning_rank': 1
                                } for m in material_list]
                    
                    # 反向模式：向所有连接的服务器发送
                    material_names = [m.get('name', f"材质{m.get('id', 'unknown')}") for m in material_list]
                    print(f"正在发送材质组 ({len(material_list)}个材质) 到已连接的服务器")
                    
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
                    print(f"向服务器 {server_id.hex()[:8]} 发送 {len(material_list)} 个材质...")
                    self.socket.send_multipart([server_id, b'', message])
                    
                    # 等待响应 - 使用事件和消息队列
                    response_timeout = self.timeout / 1000.0  # 转换为秒
                    print(f"等待服务器响应，超时时间 {response_timeout} 秒...")
                    
                    # 等待响应事件
                    if not self.response_event.wait(response_timeout):
                        print(f"等待服务器响应超时! (尝试 {retry_count+1}/{max_retries})")
                        # 增加重试次数并等待
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"将在 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        else:
                            # 最大重试次数已达到
                            return [{
                                'id': m.get('id'),
                                'name': m.get('name'),
                                'status': False,
                                'error_msg': "多次尝试后服务器仍无响应",
                                'accuracy_rank': 0,
                                'meaning_rank': 1
                            } for m in material_list]
                    
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
                                    
                                    # 从服务器响应中提取排名信息，确保同步
                                    accuracy_rank = 0  # 默认为0
                                    meaning_rank = 1  # 默认为1
                                    
                                    # 查找服务器可能返回的排名信息
                                    if response.get('material_results') and len(response['material_results']) > 0:
                                        material_result = response['material_results'][0]
                                        accuracy_rank = material_result.get('accuracy_rank', 0)
                                        meaning_rank = material_result.get('meaning_rank', 1)
                                    
                                    return [{
                                        'id': 1,
                                        'name': '未知材质',
                                        'status': status == 'Success',
                                        'error_msg': error_msg,
                                        'accuracy_rank': accuracy_rank,  # 使用服务器返回的排名
                                        'meaning_rank': meaning_rank
                                    }]
                        else:
                            print(f"收到来自未预期服务器的响应: {recv_server_id.hex()[:8]}")
                            # 增加重试计数
                            retry_count += 1
                            if retry_count < max_retries:
                                print(f"将在 {retry_delay} 秒后重试...")
                                time.sleep(retry_delay)
                                continue
                            
                    except queue.Empty:
                        print("警告：响应事件被触发但队列为空")
                        # 增加重试计数
                        retry_count += 1
                        if retry_count < max_retries:
                            print(f"将在 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        
                    # 如果到这里还没有返回，说明出现了问题
                    print(f"处理响应时遇到问题，第 {retry_count+1}/{max_retries} 次尝试")
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"将在 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        print("达到最大重试次数，返回空结果")
                        return []
                    
                else:
                    # 传统模式：直接发送到服务器
                    material_names = [m.get('name', f"材质{m.get('id', 'unknown')}") for m in material_list]
                    print(f"正在发送材质组 ({len(material_list)}个材质) 到 {self.server_address}:{self.port}")
                    self.socket.send(message)
                    
                    # 等待响应
                    print("等待服务器响应...")
                    response_data = self.socket.recv()
                    response = msgpack.unpackb(response_data, raw=False)
                    # 如果是自定义映射结果（包含 status 或 meaning_rank），直接返回该映射
                    if isinstance(response, dict):
                        if 'status' in response or 'meaning_rank' in response:
                            # 返回用户请求的字段映射
                            return {k: response[k] for k in response if k not in ('session_id','taskid','material_results','timestamp')}
                        # 否则按旧版处理
                        return response.get('material_results', [])
                    return response
                    
            except zmq.ZMQError as e:
                last_error = e
                # 只有 "Resource temporarily unavailable" 和常见的通信错误才重试
                error_str = str(e)
                retry_needed = False
                
                # 检查是否为常见的临时通信错误
                if "Resource temporarily unavailable" in error_str:
                    print(f"ZMQ通信错误: 资源暂时不可用 (尝试 {retry_count+1}/{max_retries})")
                    retry_needed = True
                elif "Operation cannot be accomplished in current state" in error_str:
                    print(f"ZMQ通信错误: 操作无法在当前状态下完成 (尝试 {retry_count+1}/{max_retries})")
                    # 需要重新创建连接
                    try:
                        self.socket.close(linger=10)
                        self.socket = self.context.socket(zmq.REQ)
                        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout)
                        self.socket.setsockopt(zmq.SNDTIMEO, self.timeout)
                        self.socket.connect(f"tcp://{self.server_address}:{self.port}")
                        print(f"已重新创建连接到 {self.server_address}:{self.port}")
                        retry_needed = True
                    except Exception as reconnect_error:
                        print(f"重新创建连接失败: {reconnect_error}")
                elif "Connection refused" in error_str or "Connection reset" in error_str:
                    print(f"ZMQ通信错误: 连接被拒绝或重置 (尝试 {retry_count+1}/{max_retries})")
                    retry_needed = True
                
                if retry_needed:
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"将在 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                        print(f"开始第 {retry_count+1}/{max_retries} 次尝试...")
                        continue
                    else:
                        print(f"达到最大重试次数 {max_retries}，放弃重试")
                
                # 达到最大重试或其他错误
                print(f"发送材质数据失败: {e} (已尝试 {retry_count} 次)")
                return [{
                    'id': m.get('id'),
                    'name': m.get('name'),
                    'status': False,
                    'error_msg': f"多次尝试后通信错误: {str(e)}",
                    'accuracy_rank': 0,
                    'meaning_rank': 1
                } for m in material_list]
        
        # 如果所有重试都失败了
        print(f"经过 {max_retries} 次重试后仍失败，最后错误: {last_error}")
        return [{
            'id': m.get('id'),
            'name': m.get('name'),
            'status': False, 
            'error_msg': f"经过 {max_retries} 次重试后仍失败: {last_error}",
            'accuracy_rank': 0,
            'meaning_rank': 1
        } for m in material_list]

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

def send_materials_json_to_blender(materials_json, server_address="localhost", port=5555, reverse_mode=False, timeout=15000):
    """发送JSON格式的多个材质到Blender服务器
    
    支持新版格式：
    {
        "head": {"input": "...", "taskid": "...", "request": [...]},
        "outputs": [{...}, {...}]
    }
    
    也支持旧版格式：
    [{"name": "...", "code": "..."}, {...}]
    
    Returns:
        如果请求了特定字段(如status, meaning_rank)，则返回映射字典
        否则返回材质结果列表
    """
    max_retries = 5  # 最大重试次数
    retry_delay = 1  # 重试间隔(秒)
    
    try:
        # 支持新版 dict 格式与旧版 list 格式
        if isinstance(materials_json, dict):
            # 对于新格式，保留完整结构
            data = materials_json.copy()
            material_list = data.get('outputs', [])
        else:
            # 对于旧版，转换为简单材质组
            material_list = materials_json
            data = {"outputs": material_list}
        
        # 验证材质列表
        for idx, material in enumerate(material_list):
            if not isinstance(material, dict) or "name" not in material or "code" not in material:
                return [{'status': False, 'error_msg': f"材质 #{idx+1} 格式错误：缺少name或code字段"}]
        
        retry_count = 0
        last_result = None
        
        # 重试循环
        while retry_count < max_retries:
            try:
                # 连接服务器
                sender = MaterialSender(server_address=server_address, port=port, reverse_mode=reverse_mode, timeout=timeout)
                if not sender.connect():
                    error_msg = f"无法连接到Blender服务器 (尝试 {retry_count+1}/{max_retries})"
                    print(error_msg)
                    retry_count += 1
                    time.sleep(retry_delay)
                    continue
                
                # 发送请求
                results = sender.send_material_group(data)
                sender.close()
                
                # 检查结果是否有效
                if results is None or (isinstance(results, list) and len(results) == 0):
                    print(f"收到空结果 (尝试 {retry_count+1}/{max_retries})，将重试...")
                    last_result = results  # 保存最后一次结果
                    retry_count += 1
                    time.sleep(retry_delay)
                else:
                    # 如果结果有效，直接返回
                    return results
            
            except Exception as e:
                print(f"第 {retry_count+1}/{max_retries} 次尝试时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                retry_count += 1
                time.sleep(retry_delay)
        
        # 所有重试都失败了
        print(f"经过 {max_retries} 次尝试后仍然失败")
        if last_result is not None:
            print("返回最后收到的结果")
            return last_result
        else:
            return [{'status': False, 'error_msg': f"多次尝试后仍无法获取有效响应"}]
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return [{'status': False, 'error_msg': f"发送材质时出错: {str(e)}"}]

class ClientSender:
    """客户端发送器，提供持久化连接和重试机制
    
    该类封装了MaterialSender，同时提供了与send_materials_json_to_blender相同的数据验证和重试功能。
    主要优势是允许创建一个实例后多次发送材质数据，而不必每次都重新建立连接。
    """
    
    def __init__(self, server_address="localhost", port=5555, reverse_mode=False, timeout=15000, max_retries=5, retry_delay=1):
        """初始化客户端发送器
        
        Args:
            server_address: 服务器地址，默认localhost
            port: 服务器端口，默认5555
            reverse_mode: 是否使用反向连接模式，默认False
            timeout: 超时时间(毫秒)，默认15000
            max_retries: 最大重试次数，默认5
            retry_delay: 重试间隔(秒)，默认1
        """
        self.server_address = server_address
        self.port = port
        self.reverse_mode = reverse_mode
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 初始化MaterialSender但不立即连接
        self.sender = None
        self.connected = False
    
    def connect(self):
        """连接到服务器，如果已连接则忽略
        
        Returns:
            bool: 连接是否成功
        """
        if self.connected and self.sender:
            print("已经连接到服务器")
            return True
            
        try:
            # 创建新的MaterialSender实例
            self.sender = MaterialSender(
                server_address=self.server_address,
                port=self.port,
                reverse_mode=self.reverse_mode,
                timeout=self.timeout
            )
            
            # 尝试连接
            if self.sender.connect():
                self.connected = True
                print(f"已连接到服务器 {self.server_address}:{self.port}")
                return True
            else:
                self.connected = False
                print(f"无法连接到服务器 {self.server_address}:{self.port}")
                return False
                
        except Exception as e:
            self.connected = False
            print(f"连接服务器时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def close(self):
        """关闭连接，释放资源"""
        if self.sender and self.connected:
            try:
                self.sender.close()
                print("连接已关闭")
            except Exception as e:
                print(f"关闭连接时出错: {str(e)}")
            finally:
                self.connected = False
                self.sender = None
    
    def send_materials(self, materials_json):
        """发送材质数据到Blender服务器
        
        这个方法结合了send_materials_json_to_blender的格式处理和重试机制，
        同时保持连接状态，避免重复建立连接。
        
        Args:
            materials_json: 包含材质数据的字典或列表
            
        Returns:
            list或dict: 包含处理结果的列表或字典
        """
        # 支持新版 dict 格式与旧版 list 格式
        if isinstance(materials_json, dict):
            # 对于新格式，保留完整结构
            data = materials_json.copy()
            material_list = data.get('outputs', [])
        else:
            # 对于旧版，转换为简单材质组
            material_list = materials_json
            data = {"outputs": material_list}
        
        # 验证材质列表
        for idx, material in enumerate(material_list):
            if not isinstance(material, dict) or "name" not in material or "code" not in material:
                return [{'status': False, 'error_msg': f"材质 #{idx+1} 格式错误：缺少name或code字段"}]
        
        # 确保已连接
        if not self.connected:
            retry_count = 0
            while retry_count < self.max_retries:
                print(f"尝试连接服务器... ({retry_count+1}/{self.max_retries})")
                if self.connect():
                    break
                retry_count += 1
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
            
            if not self.connected:
                return [{'status': False, 'error_msg': f"经过 {self.max_retries} 次尝试后仍无法连接到服务器"}]
        
        # 发送请求，带重试
        retry_count = 0
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                print(f"发送材质组数据... ({retry_count+1}/{self.max_retries})")
                results = self.sender.send_material_group(data)
                
                # 检查结果有效性
                if results is None or (isinstance(results, list) and len(results) == 0):
                    print(f"收到空结果，将重试...")
                    retry_count += 1
                    time.sleep(self.retry_delay)
                    continue
                
                # 如果结果有效，直接返回
                return results
                
            except Exception as e:
                last_error = e
                print(f"发送材质时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                
                # 检查是否是连接问题，如果是则尝试重新连接
                if "ZMQError" in str(e) or "Connection" in str(e):
                    print("尝试重新建立连接...")
                    self.close()  # 关闭现有连接
                    if not self.connect():
                        print("重新连接失败")
                    
                retry_count += 1
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
        
        # 所有重试都失败了
        error_msg = f"经过 {self.max_retries} 次尝试后仍然失败: {last_error}"
        print(error_msg)
        return [{'status': False, 'error_msg': error_msg}]
    
    def __enter__(self):
        """支持with语句上下文管理"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时自动关闭"""
        self.close()


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
