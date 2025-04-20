import bpy
import os
import ast
import zmq
import msgpack
import threading
import traceback
import time
import datetime
import json
from pathlib import Path

from ..GPT_API import image_ranking_api


OUTPUT_DIR = "/Users/ziqi/Downloads/BlenderLLM/BlenderOPT"

class MaterialDataReceiver:
    """材质数据接收器，使用ZeroMQ接收来自其他计算机的材质数据
    
    支持两种连接模式：
    1. 传统模式：作为服务端等待客户端连接（REP）
    2. 反向连接：主动作为客户端连接到公网上的接收方（DEALER）
    
    支持处理材质组：可以一次处理多个材质并返回结果列表
    """
    
    def __init__(self, port=5555, client_address=None, reverse_mode=False):
        """初始化ZeroMQ服务器
        
        Args:
            port: ZeroMQ服务器端口，默认5555
            client_address: 客户端地址（仅反向模式使用）
            reverse_mode: 是否使用反向连接模式
        """
        self.port = port
        self.client_address = client_address
        self.reverse_mode = reverse_mode
        self.context = zmq.Context()
        
        if reverse_mode:
            # 反向连接模式：使用DEALER套接字主动连接到客户端
            self.socket = self.context.socket(zmq.DEALER)
            # 为了识别当前服务端，设置身份标识
            self.socket.setsockopt(zmq.IDENTITY, f"blender-server-{bpy.app.version_string}".encode())
            # 设置关闭时行为
            self.socket.setsockopt(zmq.LINGER, 500)  # 设置延迟关闭时间为500毫秒
        else:
            # 传统模式：使用REP套接字等待连接
            self.socket = self.context.socket(zmq.REP)
            self.socket.setsockopt(zmq.LINGER, 500)  # 同样设置延迟关闭
        
        self.running = False
        self.thread = None
        self.heartbeat_thread = None
        self.connection_status = False
        
        # 添加线程安全的事件，用于同步线程关闭
        self.shutdown_event = threading.Event()
        self.response_cache = {}  # 缓存请求原始消息到响应数据
        self.full_results_cache = {}  # 缓存 taskid 到完整排序结果

    def start(self):
        """启动服务器线程"""
        if self.thread is not None and self.thread.is_alive():
            print("服务器已经在运行")
            return
            
        self.running = True
        self.shutdown_event.clear()
        self.thread = threading.Thread(target=self._run_server)
        self.thread.daemon = True
        self.thread.start()
        
        if self.reverse_mode:
            print(f"材质数据服务已启动，正在连接到客户端: {self.client_address}:{self.port}")
            # 启动心跳线程以保持连接
            self.heartbeat_thread = threading.Thread(target=self._run_heartbeat)
            self.heartbeat_thread.daemon = True
            self.heartbeat_thread.start()
        else:
            print(f"材质数据接收服务已启动，监听端口: {self.port}")
    
    def stop(self):
        """停止服务器线程"""
        try:
            print("正在停止材质数据服务...")
            
            # 设置停止标志
            self.running = False
            self.shutdown_event.set()
            
            # 等待并关闭线程
            if self.thread:
                print("正在等待主线程终止...")
                self.thread.join(timeout=2.0)
                if self.thread.is_alive():
                    print("警告：服务线程未能在预期时间内终止")
            
            if self.heartbeat_thread:
                print("正在等待心跳线程终止...")
                self.heartbeat_thread.join(timeout=2.0)
                if self.heartbeat_thread.is_alive():
                    print("警告：心跳线程未能在预期时间内终止")
            
            # 安全关闭连接
            if self.reverse_mode and self.connection_status:
                print("正在断开与客户端的连接...")
                try:
                    if hasattr(self, 'socket') and self.socket:
                        connection_string = f"tcp://{self.client_address}:{self.port}"
                        self.socket.disconnect(connection_string)
                except Exception as e:
                    print(f"断开连接时出错: {e}")
            
            # 关闭ZMQ资源
            print("正在关闭ZMQ套接字...")
            if hasattr(self, 'socket') and self.socket:
                self.socket.close(linger=100)  # 使用较短的延迟时间
                self.socket = None
            
            print("正在终止ZMQ上下文...")
            if hasattr(self, 'context') and self.context:
                self.context.term()
                self.context = None
                
            print("材质数据服务已停止")
            
        except Exception as e:
            print(f"停止服务时出错: {e}")
            traceback.print_exc()
    
    def _run_heartbeat(self):
        """发送心跳包以保持连接（仅反向模式使用）"""
        while self.running and not self.shutdown_event.is_set():
            try:
                if self.connection_status and hasattr(self, 'socket') and self.socket is not None:
                    # 发送心跳包
                    self.socket.send_multipart([b'', b'PING'])
                # 心跳间隔10秒，但每秒检查一次是否应该关闭
                for _ in range(10):
                    if self.shutdown_event.wait(1.0):
                        # 如果收到关闭信号，立即退出
                        return
            except Exception as e:
                if self.running:  # 只在正常运行状态下报告错误
                    print(f"心跳发送错误: {e}")
                time.sleep(1)  # 发生错误时稍微等待一下再继续
    
    def _run_server(self):
        """服务器线程主函数"""
        try:
            if self.reverse_mode:
                # 反向模式：连接到客户端
                connection_string = f"tcp://{self.client_address}:{self.port}"
                print(f"连接到客户端: {connection_string}")
                self.socket.connect(connection_string)
                self.connection_status = True
            else:
                # 传统模式：绑定到所有接口
                self.socket.bind(f"tcp://*:{self.port}")
            
            while self.running and not self.shutdown_event.is_set():
                try:
                    # 等待接收数据，设置超时以便能够定期检查running标志
                    if not self.socket.poll(timeout=1000, flags=zmq.POLLIN):
                        continue
                    
                    # 检查是否需要停止
                    if not self.running or self.shutdown_event.is_set():
                        break
                    
                    # 接收数据
                    if self.reverse_mode:
                        # 反向模式：接收多部分消息
                        try:
                            parts = self.socket.recv_multipart()
                            if len(parts) != 2:
                                print(f"警告: 收到格式不正确的消息，部分数量: {len(parts)}")
                                continue
                            _, message = parts
                        except Exception as e:
                            print(f"接收消息时出错: {e}")
                            continue
                    else:
                        # 传统模式：直接接收消息
                        message = self.socket.recv()
                    # 检查缓存，若为重复请求，则直接返回缓存结果
                    if message in self.response_cache:
                        cached_data = self.response_cache[message]
                        print("检测到重复请求，直接返回缓存结果")
                        if self.reverse_mode and hasattr(self, 'socket') and self.socket:
                            self.socket.send_multipart([b'', cached_data])
                        else:
                            self.socket.send(cached_data)
                        continue
                    print("接收到材质数据请求")
                    # 解析MessagePack数据
                    try:
                        data = msgpack.unpackb(message, raw=False)
                        # 保存客户端请求的问题，用于生成 Prompt
                        self.last_questions = data.get('head', {}).get('input', '')
                        session_id = data.get('session_id', 'unknown')
                        # 根据请求格式选择材质组字段
                        if 'outputs' in data or 'material_group' in data:
                            # 支持新版 'outputs' 或旧版 'material_group'
                            material_group = data.get('outputs', data.get('material_group', []))
                            head = data.get('head', {})
                            taskid = head.get('taskid')
                            request_fields = head.get('request', [])
                            # 如果 request_fields 为空或包含 'all'，则返回所有字段
                            if not request_fields or 'all' in request_fields:
                                request_fields = ['accuracy_rank', 'meaning_rank', 'status', 'error_msg', 'id', 'name']
                            print(f"接收到材质组，共 {len(material_group)} 个材质，会话ID: {session_id}, taskid: {taskid}, request: {request_fields}")
                            # 缓存单次处理结果，避免重复执行
                            if taskid not in self.full_results_cache:
                                # 执行材质组处理，获取结果和 raw 输出
                                proc_output = self._process_material_group(material_group)
                                # 保存到缓存，包括 results 和 raw 输出
                                self.full_results_cache[taskid] = proc_output
                                # 限制缓存大小, 最多保留10个任务, 删除最老的
                                if len(self.full_results_cache) > 10:
                                    oldest_task = next(iter(self.full_results_cache))
                                    del self.full_results_cache[oldest_task]
                            else:
                                proc_output = self.full_results_cache[taskid]
                            # 从 proc_output 中获取列表和 raw 输出
                            full_results = proc_output['results']
                            accuracy_raw = proc_output.get('accuracy_raw')
                            meaning_raw = proc_output.get('meaning_raw')
                            # 根据 request_fields 构建定制化响应
                            response = {'session_id': session_id, 'taskid': taskid}
                            for field in request_fields:
                                if field in ['accuracy_rank', 'meaning_rank', 'status', 'error_msg', 'id', 'name']:
                                    mapping = {r['name']: r.get(field) for r in full_results}
                                    response[field] = mapping
                                else:
                                    # 未知字段，忽略或设置为None
                                    response[field] = None
                            # 只有当 request_fields 为空 或者 包含 'all' 时才添加 raw 输出信息
                            if not request_fields or 'all' in request_fields:
                                print("检测到空请求字段或包含'all'，添加完整的排序输出信息")
                                response['accuracy_output'] = accuracy_raw
                                response['meaning_output'] = meaning_raw
                            else:
                                print(f"检测到特定请求字段: {request_fields}，不添加排序输出信息")
                        else:
                            # 兼容旧格式
                            material_code = data.get('material_code')
                            material_name = data.get('material_name', 'imported_material')
                            print(f"接收到单个材质: {material_name}，会话ID: {session_id}")
                            
                            if not material_code:
                                response = {
                                    'status': 'failed',
                                    'error_msg': '没有接收到材质代码',
                                    'session_id': session_id,
                                    'material_results': []
                                }
                            else:
                                # 在主线程中处理材质创建
                                success, error_msg = self._process_material(material_code, material_name)
                                
                                response = {
                                    'status': 'Success' if success else 'failed',
                                    'error_msg': error_msg,
                                    'session_id': session_id,
                                    'material_results': [{
                                        'id': 1,
                                        'name': material_name,
                                        'status': success,
                                        'error_msg': error_msg,
                                        'accuracy_rank': 1,
                                        'meaning_rank': 1
                                    }]
                                }
                            
                    except Exception as e:
                        print(f"处理材质数据时出错: {str(e)}")
                        traceback.print_exc()
                        response = {
                            'status': 'failed',
                            'error_msg': f"处理材质数据时出错: {str(e)}",
                            'session_id': 'unknown',
                            'material_results': [{
                                'id': 0,
                                'name': '错误',
                                'status': False,
                                'error_msg': f"处理材质数据时出错: {str(e)}",
                                'accuracy_rank': 1,
                                'meaning_rank': 1
                            }]
                        }
                    
                    # 如果在处理过程中被请求关闭，则不再发送响应
                    if not self.running or self.shutdown_event.is_set():
                        break
                    
                    # 发送定制化响应
                    print("正在发送定制化处理结果...")
                    response_data = msgpack.packb(response)
                    # 缓存响应数据以便处理重复请求
                    self.response_cache[message] = response_data
                    # 发送响应
                    if self.reverse_mode:
                        # 反向模式：发送多部分消息
                        if hasattr(self, 'socket') and self.socket:
                            try:
                                # 确保响应中包含材质结果
                                material_results = response.get('material_results', [])
                                print(f"反向模式: 发送包含 {len(material_results)} 个结果的响应")
                                
                                # 打印前三个结果的详细信息，帮助调试
                                for i, result in enumerate(material_results[:3]):
                                    print(f"结果 {i+1}: ID={result.get('id')}, 名称={result.get('name')}, "
                                          f"状态={result.get('status')}")
                                
                                # 发送响应
                                self.socket.send_multipart([b'', response_data])
                                print("反向模式响应已发送")
                            except Exception as e:
                                print(f"发送响应时出错: {e}")
                                traceback.print_exc()
                    else:
                        # 传统模式：直接发送消息
                        if hasattr(self, 'socket') and self.socket:
                            material_results = response.get('material_results', [])
                            print(f"传统模式: 发送包含 {len(material_results)} 个结果的响应")
                            self.socket.send(response_data)
                            print("传统模式响应已发送")
                    
                    print("响应发送完成")
                    
                except zmq.ZMQError as e:
                    if self.running and not self.shutdown_event.is_set():
                        print(f"ZMQ错误: {str(e)}")
                        if self.reverse_mode and "Operation cannot be accomplished in current state" in str(e):
                            # 连接可能已断开，尝试重连
                            print("连接似乎已断开，尝试重新连接...")
                            self.connection_status = False
                            time.sleep(5)  # 等待5秒后尝试重连
                            try:
                                if hasattr(self, 'socket') and self.socket and not self.shutdown_event.is_set():
                                    connection_string = f"tcp://{self.client_address}:{self.port}"
                                    self.socket.disconnect(connection_string)
                                    time.sleep(1)
                                    self.socket.connect(connection_string)
                                    self.connection_status = True
                                    print("重新连接成功")
                            except Exception as re:
                                print(f"重新连接失败: {re}")
                    time.sleep(0.5)  # 避免过于频繁的错误消息
                except Exception as e:
                    if self.running and not self.shutdown_event.is_set():
                        print(f"服务器运行时出错: {str(e)}")
                        traceback.print_exc()
                    time.sleep(0.5)
            
            print("服务线程已退出主循环")
                    
        except Exception as e:
            if self.running and not self.shutdown_event.is_set():
                print(f"启动服务器时出错: {str(e)}")
                traceback.print_exc()
            
    def _process_material_group(self, material_group):
        # 获取上一次请求中的问题文本
        questions = getattr(self, 'last_questions', '')
        results = []
        print(f"开始处理 {len(material_group)} 个材质...")
        now = datetime.datetime.now()
        subdir = now.strftime("%H.%M.%S.%d.%m")
        base_dir = get_output_dir()
        group_dir = os.path.join(base_dir, subdir)
        os.makedirs(group_dir, exist_ok=True)
        self._current_group_dir = group_dir
        
        # 存储成功渲染的图片路径和对应的材质索引
        successful_images = []
        
        for idx, material in enumerate(material_group):
            if not self.running or self.shutdown_event.is_set():
                break
            material_id = material.get('id', idx + 1)
            material_name = material.get('name', f"材质{material_id}")
            material_code = material.get('code', '')
            print(f"处理材质 [{idx+1}/{len(material_group)}]: {material_name} (ID: {material_id})")
            safe_name = material_name.replace('/', '_').replace('\\', '_')
            code_path = os.path.join(group_dir, f"{safe_name}.py")
            try:
                with open(code_path, 'w', encoding='utf-8') as f:
                    f.write(material_code)
            except Exception as e:
                print(f"保存代码文件失败: {e}")
            if not material_code:
                results.append({
                    'name': material_name,
                    'status': False,
                    'error_msg': '没有提供材质代码',
                    'accuracy_rank': 0,  # 没有代码的设为0
                    'meaning_rank': 1
                })
                continue
            success, error_msg = self._process_material(material_code, material_name)                # 构建结果对象
            result = {
                'name': material_name,
                'status': success,
                'error_msg': '' if success else error_msg,
                'accuracy_rank': 0,  # 默认设置为0，之后根据排名更新
                'meaning_rank': 0  # 默认设置为0，之后根据排名更新
            }
            results.append(result)# 如果成功，记录图片路径
            if success:
                # 对于API排序，我们需要创建一个一致的图片引用
                # 直接使用材质名称作为图片引用名称，这样更容易匹配回原始材质
                image_path = os.path.join(group_dir, f"{safe_name}.png")
                if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                    # 使用材质的原始名称而非序号来命名，便于后续匹配
                    # 避免使用序号命名可能导致的匹配问题
                    image_name = material_name  
                    successful_images.append({
                        'path': image_path,
                        'index': len(results) - 1,  # 记录对应的结果索引
                        'name': image_name,  # 直接使用材质名称作为图片引用
                        'id': material_id  # 保存材质ID以便后续排序
                    })
                    print(f"找到有效图片: {image_path}, 材质名: {image_name}, ID: {material_id}")
                else:
                    print(f"警告: 图片生成失败或为空 - {image_path}")
                time.sleep(0.1)
        
        # 处理图片排序
        if len(successful_images) > 1:
            try:
                print(f"开始对 {len(successful_images)} 个成功渲染的图片进行排序...")
                
                # 收集图片路径用于API调用
                image_paths = [img['path'] for img in successful_images]
                
                # 检验图片是否确实存在
                for i, img in enumerate(successful_images):
                    path = img['path']
                    if os.path.exists(path) and os.path.getsize(path) > 0:
                        print(f"  确认图片 {i+1}: {path} 存在且不为空, 材质名: {img['name']}")
                    else:
                        print(f"  警告: 图片 {i+1}: {path} 不存在或为空, 材质名: {img['name']}")
                
                # ============= 并行调用排序API =============
                # 动态生成提示词，使用请求中的 questions，并根据图片数量设置最大排名
                num_images = len(image_paths)
                accuracy_prompt = f"请根据以下图片与\"{questions}\"这一具体概念的相似程度进行排序，排序结果为1（最相似）到{num_images}（最不相似）。请考虑图像中的形状、颜色以及其他视觉元素来判断每个图片与\"{questions}\"这一概念的匹配程度。"
                meaning_prompt = f"请根据以下图片的意义程度进行排序，排序结果为1（最有意义）到{num_images}（最没有意义）。请考虑图像中的形状、颜色以及其他视觉元素、美学程度来进行判断。"
                    
                # 准备并发调用
                accuracy_result = [None]
                meaning_result = [None]
                def call_accuracy():
                    try:
                        accuracy_result[0] = image_ranking_api(image_paths=image_paths, uer_prompt=accuracy_prompt)
                    except Exception as e:
                        print(f"accuracy_rank 并行API调用出错: {e}")
                        traceback.print_exc()
                        accuracy_result[0] = None

                def call_meaning():
                    try:
                        meaning_result[0] = image_ranking_api(image_paths=image_paths, uer_prompt=meaning_prompt)
                    except Exception as e:
                        print(f"meaning_rank 并行API调用出错: {e}")
                        traceback.print_exc()
                        meaning_result[0] = None

                # 启动线程
                thread_acc = threading.Thread(target=call_accuracy)
                thread_mean = threading.Thread(target=call_meaning)
                thread_acc.start()
                thread_mean.start()
                thread_acc.join()
                thread_mean.join()

                # 获取结果
                accuracy_ranking_result = accuracy_result[0]
                meaning_ranking_result = meaning_result[0]
                
                # 处理 accuracy_rank 的排序
                if accuracy_ranking_result:
                    try:
                        accuracy_json = json.loads(accuracy_ranking_result)
                        print(f"accuracy_rank 解析为JSON成功，包含字段: {list(accuracy_json.keys())}")
                        
                        if "final_ranking" in accuracy_json:
                            final_ranking = accuracy_json["final_ranking"]
                            print(f"accuracy_rank 排序结果: {final_ranking}")
                            
                            # 创建材质名称与结果索引的映射
                            material_name_to_index = {}
                            for img in successful_images:
                                material_name_to_index[img['name']] = img['index']
                            
                            # 尝试直接匹配材质名称
                            print("尝试直接按材质名称匹配 accuracy_rank 排序结果...")
                            matches_found = False
                            
                            # 直接根据排序结果中的位置分配排名
                            for rank, name in enumerate(final_ranking, 1):
                                # 尝试直接匹配材质名称
                                matched = False
                                for img in successful_images:
                                    # 检查是否匹配材质名称或者提取的序号
                                    if img['name'] == name or name.startswith(f"M{img['id']}"):
                                        results[img['index']]['accuracy_rank'] = rank
                                        print(f"材质 {img['name']} (ID:{img['id']}) accuracy_rank 设为 {rank}")
                                        matched = True
                                        matches_found = True
                                        break
                                
                                if not matched:
                                    print(f"警告: 无法为 accuracy_rank 排序结果 '{name}' 找到对应的材质")
                            
                            # 如果没有成功匹配任何材质，尝试按序号顺序分配
                            if not matches_found:
                                print("未找到直接匹配，按序号顺序分配 accuracy_rank...")
                                # 根据排序结果长度和材质数量，尝试按顺序分配
                                min_len = min(len(final_ranking), len(successful_images))
                                
                                # 按顺序分配排名
                                for i in range(min_len):
                                    rank = i + 1
                                    img = successful_images[i]
                                    results[img['index']]['accuracy_rank'] = rank
                                    print(f"材质 {img['name']} (ID:{img['id']}) 分配 accuracy_rank {rank}")
                                
                        else:
                            print(f"警告: accuracy_rank 排序结果中没有 final_ranking 字段，只有: {list(accuracy_json.keys())}")
                            # 如果没有排序结果，手动分配排名
                            for i, img in enumerate(successful_images):
                                rank = i + 1
                                results[img['index']]['accuracy_rank'] = rank
                                print(f"因无排序结果，材质 {img['name']} (ID:{img['id']}) 手动分配 accuracy_rank {rank}")
                                
                    except json.JSONDecodeError as e:
                        print(f"解析 accuracy_rank 排序结果出错: {e}")
                        print(f"原始结果: {accuracy_ranking_result[:200]}...")  # 只打印前200个字符
                        # 手动分配排名
                        for i, img in enumerate(successful_images):
                            rank = i + 1
                            results[img['index']]['accuracy_rank'] = rank
                            print(f"因解析错误，材质 {img['name']} (ID:{img['id']}) 手动分配 accuracy_rank {rank}")
                else:
                    # 如果API调用失败，手动分配排名
                    for i, img in enumerate(successful_images):
                        rank = i + 1
                        results[img['index']]['accuracy_rank'] = rank
                        print(f"因API调用失败，材质 {img['name']} (ID:{img['id']}) 手动分配 accuracy_rank {rank}")
                
                # ============= 接着处理 meaning_rank =============
                if meaning_ranking_result:
                    try:
                        meaning_json = json.loads(meaning_ranking_result)
                        print(f"meaning_rank 解析为JSON成功，包含字段: {list(meaning_json.keys())}")
                        
                        if "final_ranking" in meaning_json:
                            final_ranking = meaning_json["final_ranking"]
                            print(f"meaning_rank 排序结果: {final_ranking}")
                            
                            # 创建材质名称与结果索引的映射
                            material_name_to_index = {}
                            for img in successful_images:
                                material_name_to_index[img['name']] = img['index']
                            
                            # 尝试直接匹配材质名称
                            print("尝试直接按材质名称匹配 meaning_rank 排序结果...")
                            matches_found = False
                            
                            # 直接根据排序结果中的位置分配排名
                            for rank, name in enumerate(final_ranking, 1):
                                # 尝试直接匹配材质名称
                                matched = False
                                for img in successful_images:
                                    # 检查是否匹配材质名称或者提取的序号
                                    if img['name'] == name or name.startswith(f"M{img['id']}"):
                                        results[img['index']]['meaning_rank'] = rank
                                        print(f"材质 {img['name']} (ID:{img['id']}) meaning_rank 设为 {rank}")
                                        matched = True
                                        matches_found = True
                                        break
                                
                                if not matched:
                                    print(f"警告: 无法为 meaning_rank 排序结果 '{name}' 找到对应的材质")
                            
                            # 如果没有成功匹配任何材质，尝试按序号顺序分配
                            if not matches_found:
                                print("未找到直接匹配，按序号顺序分配 meaning_rank...")
                                # 根据排序结果长度和材质数量，尝试按顺序分配
                                min_len = min(len(final_ranking), len(successful_images))
                                
                                # 按顺序分配排名
                                for i in range(min_len):
                                    rank = i + 1
                                    img = successful_images[i]
                                    results[img['index']]['meaning_rank'] = rank
                                    print(f"材质 {img['name']} (ID:{img['id']}) 分配 meaning_rank {rank}")
                                
                        else:
                            print(f"警告: meaning_rank 排序结果中没有 final_ranking 字段，只有: {list(meaning_json.keys())}")
                            # 如果没有排序结果，手动分配排名
                            for i, img in enumerate(successful_images):
                                rank = i + 1
                                results[img['index']]['meaning_rank'] = rank
                                print(f"因无排序结果，材质 {img['name']} (ID:{img['id']}) 手动分配 meaning_rank {rank}")
                                
                    except json.JSONDecodeError as e:
                        print(f"解析 meaning_rank 排序结果出错: {e}")
                        print(f"原始结果: {meaning_ranking_result[:200]}...")  # 只打印前200个字符
                        # JSON解析错误时也手动分配排名
                        for i, img in enumerate(successful_images):
                            rank = i + 1
                            results[img['index']]['meaning_rank'] = rank
                            print(f"因解析错误，材质 {img['name']} (ID:{img['id']}) 手动分配 meaning_rank {rank}")
                else:
                    # 如果API调用失败，手动分配排名
                    for i, img in enumerate(successful_images):
                        rank = i + 1
                        results[img['index']]['meaning_rank'] = rank
                        print(f"因API调用失败，材质 {img['name']} (ID:{img['id']}) 手动分配 meaning_rank {rank}")
                
            except Exception as e:
                print(f"排序过程中出错: {e}")
                traceback.print_exc()
                # 即使出错也手动分配排名
                for i, img in enumerate(successful_images):
                    rank = i + 1
                    results[img['index']]['accuracy_rank'] = rank
                    results[img['index']]['meaning_rank'] = rank
                    print(f"因处理错误，材质 {img['name']} (ID:{img['id']}) 手动分配排名 {rank}")
                
        elif len(successful_images) == 1:
            # 只有一张图片，直接排名第1
            img = successful_images[0]
            results[img['index']]['accuracy_rank'] = 1
            results[img['index']]['meaning_rank'] = 1
            print(f"只有一张图片，材质 {img['name']} 的排名设置为 1")
        else:
            # 没有成功渲染的图片，确保每个材质都有默认排名
            print("没有成功渲染的图片，设置默认排名")
            for idx, result in enumerate(results):
                result['accuracy_rank'] = idx + 1
                result['meaning_rank'] = idx + 1
        
        # 初始化变量以确保即使在异常情况下也有定义
        accuracy_ranking_result = None
        meaning_ranking_result = None
            
        print(f"材质组处理完成，结果数量: {len(results)}")
        # 返回结果列表以及 raw 排序输出
        return {
            'results': results,
            'accuracy_raw': accuracy_ranking_result,
            'meaning_raw': meaning_ranking_result
        }
    
    def _process_material(self, material_code, material_name):
        """处理材质数据，创建材质，并严格用 name 命名图片
        
        Args:
            material_code: 材质的Python代码
            material_name: 材质名称
            
        Returns:
            tuple: (成功标志, 错误信息)
        """
        # 首先检查是否为空文件
        if not material_code or material_code.strip() == '':
            return False, "材质代码为空"
            
        # 使用Blender的计时器在主线程中执行此函数
        result = {'success': False, 'error_msg': ''}
        
        def create_material():
            try:
                # 标记图片是否被创建
                image_created = False
                output_path = None
                
                # 检查代码语法
                try:
                    ast.parse(material_code)
                except SyntaxError as se:
                    line_no = se.lineno if hasattr(se, 'lineno') else '未知'
                    col_no = se.offset if hasattr(se, 'offset') else '未知'
                    error_msg = f"材质代码中有语法错误: 第{line_no}行，第{col_no}列: {se}"
                    result['error_msg'] = error_msg
                    return
                
                # 删除所有现有材质
                for material in list(bpy.data.materials):
                    bpy.data.materials.remove(material)
                
                # 创建命名空间
                namespace = {
                    'bpy': bpy,
                    'os': os,
                    'material_name': material_name
                }
                
                # 检查代码是否自己创建材质
                creates_own_material = "bpy.data.materials.new" in material_code
                
                # 创建材质
                material = None
                if not creates_own_material:
                    material = bpy.data.materials.new(name=material_name)
                    material.use_nodes = True
                    
                    # 清空现有节点
                    nodes = material.node_tree.nodes
                    for node in list(nodes):
                        nodes.remove(node)
                    
                    # 将材质添加到命名空间
                    namespace['material'] = material
                
                # 执行代码
                exec(material_code, namespace)
                
                # 如果代码自己创建了材质，找出新创建的材质
                if creates_own_material:
                    after_materials = set(bpy.data.materials.keys())
                    if len(after_materials) > 0:
                        material = bpy.data.materials[list(after_materials)[0]]
                        print(f"代码创建了自己的材质: {material.name}")
                
                # 自动将材质应用到名为"平面"的对象
                if material:
                    applied = False
                    for obj in bpy.data.objects:
                        if obj.type == 'MESH' and obj.name == '平面':
                            obj.data.materials.clear()
                            obj.data.materials.append(material)
                            print(f"将材质 {material.name} 应用到对象 {obj.name}")
                            applied = True
                            break
                    if not applied:
                        print("警告：场景中没有找到名为'平面'的网格对象")
                    else:
                        try:
                            scene = bpy.context.scene
                            camera = scene.camera
                            if camera is None:
                                print("未找到当前场景的摄像机，跳过渲染保存")
                            else:
                                output_dir = getattr(self, '_current_group_dir', get_output_dir())
                                os.makedirs(output_dir, exist_ok=True)
                                safe_name = material_name.replace('/', '_').replace('\\', '_')
                                output_path = os.path.join(output_dir, f"{safe_name}.png")
                                scene.render.filepath = output_path
                                bpy.ops.render.render(write_still=True, use_viewport=True)
                                print(f"渲染完成，图片已保存到: {output_path}")
                                
                                # 检查图片是否真的被创建
                                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                                    image_created = True
                                    print(f"已确认图片创建：{output_path}")
                                else:
                                    print(f"警告：图片文件不存在或为空：{output_path}")
                        except Exception as render_exc:
                            print(f"渲染或保存图片时出错: {render_exc}")
                
                # 只有当图片真正创建了才认为是成功的
                if image_created:
                    result['success'] = True
                else:
                    result['success'] = False
                    # 如果没有其他错误信息但图片未创建，判定为未运行函数
                    if not result['error_msg']:
                        result['error_msg'] = "未运行函数或未渲染图片"
                
            except Exception as e:
                error_msg = f"执行材质代码时出错: {str(e)}"
                print(error_msg)
                traceback.print_exc()
                result['error_msg'] = error_msg
            
            return None
        
        # 在主线程中执行
        bpy.app.timers.register(create_material)
        
        # 等待执行完成
        timeout = 5.0  # 最长等待5秒
        start_time = time.time()
        while not result['success'] and not result['error_msg'] and time.time() - start_time < timeout:
            # 检查是否需要中止等待
            if not self.running or self.shutdown_event.is_set():
                return False, "服务停止，中止材质处理"
            time.sleep(0.1)
        
        # 如果超时
        if not result['success'] and not result['error_msg']:
            result['error_msg'] = '处理材质超时'
        
        return result['success'], result['error_msg']

# 全局实例
_material_receiver = None

def start_receiver(port=5555, client_address=None, reverse_mode=False):
    """启动材质数据接收服务
    
    Args:
        port: 服务端口
        client_address: 客户端地址（仅反向模式使用）
        reverse_mode: 是否使用反向连接模式
    """
    global _material_receiver
    
    # 先确保停止任何现有的接收器
    stop_receiver()
    
    # 创建新的接收器
    _material_receiver = MaterialDataReceiver(port=port, client_address=client_address, reverse_mode=reverse_mode)
    _material_receiver.start()
    
def stop_receiver():
    """停止材质数据接收服务"""
    global _material_receiver
    if _material_receiver is not None:
        try:
            _material_receiver.stop()
        except Exception as e:
            print(f"停止接收器时出错: {e}")
            traceback.print_exc()
        finally:
            _material_receiver = None

def get_output_dir():
    try:
        return bpy.context.scene.ntp_options.webtrans_output_dir
    except Exception:
        return OUTPUT_DIR