from client import send_file_to_blender, send_text_to_blender, send_materials_json_to_blender, ClientSender
import uuid
import time

# 定义要发送给Blender的代码
blender_code = """
import bpy, mathutils

mat = bpy.data.materials.new(name = "Material_113")
mat.use_nodes = True
#initialize Material_111 node group
def material_111_node_group():

    material_111 = mat.node_tree
    #start with a clean node tree
    for node in material_111.nodes:
        material_111.nodes.remove(node)
    material_111.color_tag = 'NONE'
    material_111.description = ""
    material_111.default_group_node_width = 140
    

    #material_111 interface

    #initialize material_111 nodes
    #node Material Output
    material_output = material_111.nodes.new("ShaderNodeOutputMaterial")
    material_output.name = "Material Output"
    material_output.is_active_output = True
    material_output.target = 'ALL'
    #Displacement
    material_output.inputs[2].default_value = (0.0, 0.0, 0.0)
    #Thickness
    material_output.inputs[3].default_value = 0.0

    #node Principled BSDF
    principled_bsdf = material_111.nodes.new("ShaderNodeBsdfPrincipled")
    principled_bsdf.name = "Principled BSDF"
    principled_bsdf.distribution = 'MULTI_GGX'
    principled_bsdf.subsurface_method = 'RANDOM_WALK'
    #Base Color
    principled_bsdf.inputs[0].default_value = (0.8001416921615601, 0.16959014534950256, 0.5651387572288513, 1.0)
    #Metallic
    principled_bsdf.inputs[1].default_value = 0.0
    #Roughness
    principled_bsdf.inputs[2].default_value = 0.5
    #IOR
    principled_bsdf.inputs[3].default_value = 1.4500000476837158
    #Alpha
    principled_bsdf.inputs[4].default_value = 1.0
    #Normal
    principled_bsdf.inputs[5].default_value = (0.0, 0.0, 0.0)
    #Diffuse Roughness
    principled_bsdf.inputs[7].default_value = 0.0
    #Subsurface Weight
    principled_bsdf.inputs[8].default_value = 0.0
    #Subsurface Radius
    principled_bsdf.inputs[9].default_value = (1.0, 0.20000000298023224, 0.10000000149011612)
    #Subsurface Scale
    principled_bsdf.inputs[10].default_value = 0.05000000074505806
    #Subsurface Anisotropy
    principled_bsdf.inputs[12].default_value = 0.0
    #Specular IOR Level
    principled_bsdf.inputs[13].default_value = 0.5
    #Specular Tint
    principled_bsdf.inputs[14].default_value = (1.0, 1.0, 1.0, 1.0)
    #Anisotropic
    principled_bsdf.inputs[15].default_value = 0.0
    #Anisotropic Rotation
    principled_bsdf.inputs[16].default_value = 0.0
    #Tangent
    principled_bsdf.inputs[17].default_value = (0.0, 0.0, 0.0)
    #Transmission Weight
    principled_bsdf.inputs[18].default_value = 0.0
    #Coat Weight
    principled_bsdf.inputs[19].default_value = 0.0
    #Coat Roughness
    principled_bsdf.inputs[20].default_value = 0.029999999329447746
    #Coat IOR
    principled_bsdf.inputs[21].default_value = 1.5
    #Coat Tint
    principled_bsdf.inputs[22].default_value = (1.0, 1.0, 1.0, 1.0)
    #Coat Normal
    principled_bsdf.inputs[23].default_value = (0.0, 0.0, 0.0)
    #Sheen Weight
    principled_bsdf.inputs[24].default_value = 0.0
    #Sheen Roughness
    principled_bsdf.inputs[25].default_value = 0.5
    #Sheen Tint
    principled_bsdf.inputs[26].default_value = (1.0, 1.0, 1.0, 1.0)
    #Emission Color
    principled_bsdf.inputs[27].default_value = (1.0, 1.0, 1.0, 1.0)
    #Emission Strength
    principled_bsdf.inputs[28].default_value = 0.0
    #Thin Film Thickness
    principled_bsdf.inputs[29].default_value = 0.0
    #Thin Film IOR
    principled_bsdf.inputs[30].default_value = 1.3300000429153442


    #Set locations
    material_output.location = (300.0, 300.0)
    principled_bsdf.location = (10.0, 300.0)

    #Set dimensions
    material_output.width, material_output.height = 140.0, 100.0
    principled_bsdf.width, principled_bsdf.height = 240.0, 100.0

    #initialize material_111 links
    #principled_bsdf.BSDF -> material_output.Surface
    material_111.links.new(principled_bsdf.outputs[0], material_output.inputs[0])
    return material_111

material_111 = material_111_node_group()
"""


blender_code2 = """
import bpy, mathutils

mat = bpy.data.materials.new(name = "Material_113")
mat.use_nodes = True
#initialize Material_111 node group
def material_111_node_group():

    material_111 = mat.node_tree
    #start with a clean node tree
    for node in material_111.nodes:
        material_111.nodes.remove(node)
    material_111.color_tag = 'NONE'
    material_111.description = ""
    material_111.default_group_node_width = 140
    

    #material_111 interface

    #initialize material_111 nodes
    #node Material Output
    material_output = material_111.nodes.new("ShaderNodeOutputMaterial")
    material_output.name = "Material Output"
    material_output.is_active_output = True
    material_output.target = 'ALL'
    #Displacement
    material_output.inputs[2].default_value = (0.0, 0.0, 0.0)
    #Thickness
    material_output.inputs[3].default_value = 0.0

    #node Principled BSDF
    principled_bsdf = material_111.nodes.new("ShaderNodeBsdfPrincipled")
    principled_bsdf.name = "Principled BSDF"
    principled_bsdf.distribution = 'MULTI_GGX'
    principled_bsdf.subsurface_method = 'RANDOM_WALK'
    #Base Color
    principled_bsdf.inputs[0].default_value = (0.8001416921615601, 0.16959014534950256, 0.9951387572288513, 1.0)
    #Metallic
    principled_bsdf.inputs[1].default_value = 0.0
    #Roughness
    principled_bsdf.inputs[2].default_value = 0.5
    #IOR
    principled_bsdf.inputs[3].default_value = 1.4500000476837158
    #Alpha
    principled_bsdf.inputs[4].default_value = 1.0
    #Normal
    principled_bsdf.inputs[5].default_value = (0.0, 0.0, 0.0)
    #Diffuse Roughness
    principled_bsdf.inputs[7].default_value = 0.0
    #Subsurface Weight
    principled_bsdf.inputs[8].default_value = 0.0
    #Subsurface Radius
    principled_bsdf.inputs[9].default_value = (1.0, 0.20000000298023224, 0.10000000149011612)
    #Subsurface Scale
    principled_bsdf.inputs[10].default_value = 0.05000000074505806
    #Subsurface Anisotropy
    principled_bsdf.inputs[12].default_value = 0.0
    #Specular IOR Level
    principled_bsdf.inputs[13].default_value = 0.5
    #Specular Tint
    principled_bsdf.inputs[14].default_value = (1.0, 1.0, 1.0, 1.0)
    #Anisotropic
    principled_bsdf.inputs[15].default_value = 0.0
    #Anisotropic Rotation
    principled_bsdf.inputs[16].default_value = 0.0
    #Tangent
    principled_bsdf.inputs[17].default_value = (0.0, 0.0, 0.0)
    #Transmission Weight
    principled_bsdf.inputs[18].default_value = 0.0
    #Coat Weight
    principled_bsdf.inputs[19].default_value = 0.0
    #Coat Roughness
    principled_bsdf.inputs[20].default_value = 0.029999999329447746
    #Coat IOR
    principled_bsdf.inputs[21].default_value = 1.5
    #Coat Tint
    principled_bsdf.inputs[22].default_value = (1.0, 1.0, 1.0, 1.0)
    #Coat Normal
    principled_bsdf.inputs[23].default_value = (0.0, 0.0, 0.0)
    #Sheen Weight
    principled_bsdf.inputs[24].default_value = 0.0
    #Sheen Roughness
    principled_bsdf.inputs[25].default_value = 0.5
    #Sheen Tint
    principled_bsdf.inputs[26].default_value = (1.0, 1.0, 1.0, 1.0)
    #Emission Color
    principled_bsdf.inputs[27].default_value = (1.0, 1.0, 1.0, 1.0)
    #Emission Strength
    principled_bsdf.inputs[28].default_value = 0.0
    #Thin Film Thickness
    principled_bsdf.inputs[29].default_value = 0.0
    #Thin Film IOR
    principled_bsdf.inputs[30].default_value = 1.3300000429153442


    #Set locations
    material_output.location = (300.0, 300.0)
    principled_bsdf.location = (10.0, 300.0)

    #Set dimensions
    material_output.width, material_output.height = 140.0, 100.0
    principled_bsdf.width, principled_bsdf.height = 240.0, 100.0

    #initialize material_111 links
    #principled_bsdf.BSDF -> material_output.Surface
    material_111.links.new(principled_bsdf.outputs[0], material_output.inputs[0])
    return material_111

# material_111 = material_111_node_group()
"""


blender_code3 = """
import bpy, mathutils

mat = bpy.data.materials.new(name = "Material_113")
mat.use_nodes = True
#initialize Material_111 node group
def material_111_node_group():

    material_111 = mat.node_tree
    #start with a clean node tree
    for node in material_111.nodes:
        material_111.nodes.remove(node)
    material_111.color_tag = 'NONE'
    material_111.description = ""
    material_111.default_group_node_width = 140
    

    #material_111 interface

    #initialize material_111 nodes
    #node Material Output
    material_output = material_111.nodes.new("ShaderNodeOutputMaterial")
    material_output.name = "Material Output"
    material_output.is_active_output = True
    material_output.target = 'ALL'
    #Displacement
    material_output.inputs[2].default_value = (0.0, 0.0, 0.0)
    #Thickness
    material_output.inputs[3].default_value = 0.0

    #node Principled BSDF
    principled_bsdf = material_111.nodes.new("ShaderNodeBsdfPrincipled")
    principled_bsdf.name = "Principled BSDF"
    principled_bsdf.distribution = 'MULTI_GGX'
    principled_bsdf.subsurface_method = 'RANDOM_WALK'
    #Base Color
    principled_bsdf.inputs[0].default_value = (0.8001416921615601, 0.16959014534950256, 0.9951387572288513, 1.0)
    #Metallic
    principled_bsdf.inputs[1].default_value = 0.0
    #Roughness
    principled_bsdf.inputs[2].default_value = 0.5
    #IOR
    principled_bsdf.inputs[3].default_value = 1.4500000476837158
    #Alpha
    principled_bsdf.inputs[4].default_value = 1.0
    #Normal
    principled_bsdf.inputs[5].default_value = (0.0, 0.0, 0.0)
    #Diffuse Roughness
    principled_bsdf.inputs[7].default_value = 0.0
    #Subsurface Weight
    principled_bsdf.inputs[8].default_value = 0.0
    #Subsurface Radius
    principled_bsdf.inputs[9].default_value = (1.0, 0.20000000298023224, 0.10000000149011612)
    #Subsurface Scale
    principled_bsdf.inputs[10].default_value = 0.05000000074505806
    #Subsurface Anisotropy
    principled_bsdf.inputs[12].default_value = 0.0
    #Specular IOR Level
    principled_bsdf.inputs[13].default_value = 0.5
    #Specular Tint
    principled_bsdf.inputs[14].default_value = (1.0, 1.0, 1.0, 1.0)
    #Anisotropic
    principled_bsdf.inputs[15].default_value = 0.0
    #Anisotropic Rotation
    principled_bsdf.inputs[16].default_value = 0.0
    #Tangent
    principled_bsdf.inputs[17].default_value = (0.0, 0.0, 0.0)
    #Transmission Weight
    principled_bsdf.inputs[18].default_value = 0.0
    #Coat Weight
    principled_bsdf.inputs[19].default_value = 0.0
    #Coat Roughness
    principled_bsdf.inputs[20].default_value = 0.029999999329447746
    #Coat IOR
    principled_bsdf.inputs[21].default_value = 1.5
    #Coat Tint
    principled_bsdf.inputs[22].default_value = (1.0, 1.0, 1.0, 1.0)
    #Coat Normal
    principled_bsdf.inputs[23].default_value = (0.0, 0.0, 0.0)
    #Sheen Weight
    principled_bsdf.inputs[24].default_value = 0.0
    #Sheen Roughness
    principled_bsdf.inputs[25].default_value = 0.5
    #Sheen Tint
    principled_bsdf.iadwadawwdawdwadwnputs[26].default_value = (1.0, 1.0, 1.0, 1.0)
    #Emission Color
    principled_bsdf.inputs[27].default_value = (1.0, 1.0, 1.0, 1.0)
    #Emission Strength
    principled_bsdf.inputs[28].default_value = 0.0
    #Thin Film Thickness
    principled_bsdf.inputs[29].default_value = 0.0
    #Thin Film IOR
    principled_bsdf.inputs[30].default_value = 1.3300000429153442


    #Set locations
    material_output.location = (300.0, 300.0)
    principled_bsdf.location = (10.0, 300.0)

    #Set dimensions
    material_output.width, material_output.height = 140.0, 100.0
    principled_bsdf.width, prindasdawedwswdcipled_bsdf.height = 240.0, 100.0

    #initialize material_111 links
    #principled_bsdf.BSDF -> material_output.Surface
    material_111.links.new(principled_bsdf.outputs[0], material_output.inputs[0])
    return material_111

material_111 = material_111_node_group()
"""


blender_code4 = """

"""
    
# 在 materials 定义前生成唯一 taskid
taskid = uuid.uuid4().hex

print(taskid + "\n")

# 构造请求
materials1 = {
    "head": {
        "input": "创建一个红色的楼房的材质",
        "taskid": taskid, #"1c6cafdb570d4428a30e59da3a783b79", #taskid, # 得注意重定义问题。得在数据集环节就植入 taskid
        # "request": ["accuracy_rank", "meaning_rank", "error_msg"]
        "request": []
    },
    "outputs": [
        {
            "name": "M1",
            "code": blender_code3
        },
        {
            "name": "M2",
            "code": blender_code4
        },
        {
            "name": "M3",
            "code": blender_code
        },
        {
            "name": "M4",
            "code": blender_code2
        }
    ]
}


materials2 = {
    "head": {
        "input": "创建一个红色的楼房的材质",
        "taskid": taskid, #"1c6cafdb570d4428a30e59da3a783b79", #taskid, # 得注意重定义问题。得在数据集环节就植入 taskid
        "request": []
    },
    "outputs": [
        {
            "name": "M1",
            "code": blender_code3
        },
        {
            "name": "M2",
            "code": blender_code4
        },
        # {
        #     "name": "M3",
        #     "code": blender_code
        # },
        # {
        #     "name": "M4",
        #     "code": blender_code2
        # },
        # {
        #     "name": "M5",
        #     "code": blender_code2
        # }
    ]
}

# 使用ClientSender类进行持久化连接
client = ClientSender(server_address="10.30.244.17", port=5555)

# 第一次发送材质
# print("第一次发送材质...")
# response1 = client.send_materials(materials1)

# print(response1)

# time.sleep(10)

# 第二次发送材质 - 复用同一连接
print("第二次发送材质...")
response = client.send_materials(materials2)
print(response)
print(response["accuracy_rank"])
    
    




# print(response[0]['status'])