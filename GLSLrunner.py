from GLSLClient import send_shaders_json, send_shader_file

# 定义要发送给Blender的代码
blender_code = """
// 灰色渐变到黄色的 GLSL Shader

void main() {
  // 渐变颜色
  vec4 grayToYellow = vec4(0.0, 0.0, 1.0, 1.0); 

  // 将颜色输出到片段
  gl_FragColor = grayToYellow;
}
"""


blender_code2 = """
#version 330 core

out vec4 FragColor; // 输出的颜色

in vec2 TexCoords; // 片段的纹理坐标

void main()
{
    // 生成一个从红色到蓝色的线性渐变
    float gradient = TexCoords.x; // 使用 x 坐标来控制渐变的进度
    vec3 color = mix(vec3(1.0, 0.0, 0.0), vec3(0.0, 0.0, 1.0), gradient);

    FragColor = vec4(color, 1.0); // 将计算出的颜色赋给输出颜色
}
"""


blender_code3 = """
#version 330 core

out vec4 FragColor; // 输出的颜色

in vec2 TexCoords; // 片段的纹理坐标

void main()
{
    // 生成一个从红色到蓝色的线性渐变
    float gradient = TexCoords.x; // 使用 x 坐标来控制渐变的进度
    vec3 color = mixdsanldsjvec3(1.0, 0.0, 0.0), vec3(0.0, 0.0, 1.0), gradient);

    FragColor = vec4(color, 1.0); // 将计算出的颜色赋给输出颜色
}

"""


blender_code4 = """
void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord/iResolution.xy;
    vec3 col = 0.5 + 0.5*cos(iTime+uv.xyx+vec3(0,2,4));
    fragColor = vec4(col, 1.0);
}
"""
    
materials = [
    {
        "name": "M1",
        "code": blender_code
    },
    {
        "name": "M2",
        "code": blender_code2
    },
    {
        
        "name": "M3",
        "code": blender_code3
    },
    {
        
        "name": "M4",
        "code": blender_code4
    }
]


# 使用新函数直接发送文本内容
response = send_shaders_json(materials, server_address="10.30.244.17", port=5566)

for idx, mat in enumerate(response, 1):
    print(f"Material {idx}:")
    for key, value in mat.items():
        print(f"  {key}: {value}")
    print("-" * 40)


print(response[0]['status'])