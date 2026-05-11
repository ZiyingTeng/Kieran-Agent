# AI 角色对话 - 聊天界面

## 功能特性

### 1. 聊天功能
- 选择角色进行对话
- 实时发送和接收消息
- 历史记录保存

### 2. 编辑功能
- 点击"编辑"按钮进入编辑模式
- 修改后按 Enter 或点击"保存"
- 弹出确认对话框，对比原回复和新回复
- 确认后同步更新内存和历史文件

### 3. 重新生成功能
- 点击"重新生成"按钮
- AI 重新生成回复
- 直接覆盖，无需确认

## 快速开始

### 1. 启动服务器
```bash
cd /home/ps/tzy/Chatjoy2.0
python api_server_multi_expert.py
```

### 2. 打开聊天界面
```bash
# 方法1: 直接双击打开
# web/chat/index.html

# 方法2: 使用本地服务器
cd /home/ps/tzy/Chatjoy2.0/web
python -m http.server 8080
# 然后访问 http://localhost:8080/chat/
```

### 3. 开始使用
1. 选择角色
2. 发送消息
3. 对 AI 回复进行编辑或重新生成

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| Shift+Enter | 发送消息 |
| Enter | 保存编辑（在编辑模式下） |
| Esc | 取消编辑 |

## API 接口

### POST /api/mobile/chat
发送消息和重新生成

### POST /api/roles/update_history
更新聊天记录（编辑功能）

## 技术栈

- 纯 HTML + CSS + JavaScript
- 无需任何框架
- 可直接在浏览器中使用

## 目录结构

```
web/chat/
├── index.html          # 聊天界面（包含所有功能）
├── test_api.py         # API 测试脚本
└── README.md           # 本文件
```

## 注意事项

1. **跨域问题**: 如果遇到 CORS 错误，确保后端已配置允许跨域
2. **消息匹配**: 编辑功能通过用户消息内容匹配，确保消息唯一性
3. **文件权限**: 确保服务器有写入历史文件的权限
