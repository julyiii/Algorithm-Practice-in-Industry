import os
import json
import requests
import hmac
import hashlib
import base64
import urllib.parse
import time
from datetime import datetime

# 从环境变量获取配置
DINGTALK_ACCESS_TOKEN = os.environ.get("DINGTALK_ACCESS_TOKEN", "")
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET", "")
RETURN_PAPERS = int(os.environ.get("RETURN_PAPERS", "20"))

def get_latest_json_file(json_dir):
    """获取最新的JSON文件路径
    
    Args:
        json_dir: JSON文件所在目录
    
    Returns:
        str: 最新JSON文件的路径
    """
    try:
        # 获取目录中的所有JSON文件
        json_files = [f for f in os.listdir(json_dir) if f.endswith('.json') and f != 'results.json']
        if not json_files:
            print("未找到JSON文件")
            return None
        
        # 按文件名（日期）排序，获取最新的
        json_files.sort(reverse=True)
        latest_file = json_files[0]
        return os.path.join(json_dir, latest_file)
    except Exception as e:
        print(f"获取最新JSON文件失败: {e}")
        return None

def load_paper_data(file_path):
    """加载并解析论文数据
    
    Args:
        file_path: JSON文件路径
    
    Returns:
        list: 论文数据列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 转换为列表并添加arxiv_id字段
        papers = []
        for arxiv_id, paper_info in data.items():
            paper_info['arxiv_id'] = arxiv_id
            papers.append(paper_info)
        
        return papers
    except Exception as e:
        print(f"加载论文数据失败: {e}")
        return []

def send_papers_to_dingding(papers):
    """发送论文到钉钉
    
    Args:
        papers: 论文数据列表
    """
    # 检查配置
    if not DINGTALK_ACCESS_TOKEN or not DINGTALK_SECRET:
        print("⚠️ 环境变量 DINGTALK_ACCESS_TOKEN 或 DINGTALK_SECRET 未设置，无法发送钉钉消息")
        return
    
    date = datetime.now().strftime('%Y-%m-%d')
    
    # 构建消息内容
    msg_lines = [f"## 📚 每日论文推送 - {date}"]
    
    for idx, paper in enumerate(papers, 1):
        title = paper['title']
        translation = paper.get('translation', 'N/A')
        score = paper.get('rerank_relevance_score', 'N/A')
        summary = paper.get('summary', 'N/A')
        url = paper['url']
        
        # 构建评分显示
        if isinstance(score, int):
            score_display = "⭐️" * score + f" {score}分"
        else:
            score_display = "N/A"
        
        msg_lines.append(f"\n### {idx}. {title}")
        msg_lines.append(f"**评分**: {score_display}")
        msg_lines.append(f"**翻译**: {translation}")
        msg_lines.append(f"**摘要**: {summary}")
        msg_lines.append(f"**链接**: [{url}]({url})")
    
    msg_content = "\n".join(msg_lines)
    
    # 生成签名
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f'{timestamp}\n{DINGTALK_SECRET}'
    hmac_code = hmac.new(DINGTALK_SECRET.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    
    url = f'https://oapi.dingtalk.com/robot/send?access_token={DINGTALK_ACCESS_TOKEN}&timestamp={timestamp}&sign={sign}'
    
    body = {
        "at": {
            "isAtAll": False,
            "atUserIds": [],
            "atMobiles": []
        },
        "markdown": {
            "title": "每日论文推送",
            "text": msg_content
        },
        "msgtype": "markdown"
    }
    
    headers = {'Content-Type': 'application/json'}
    
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        result = resp.json()
        print(f"✉️ 钉钉推送返回状态: {resp.status_code}")
        print(f"📋 响应内容: {result}")
        
        if result.get('errcode') == 0:
            print("✅ 钉钉消息发送成功！")
        else:
            print(f"❌ 钉钉消息发送失败: {result.get('errmsg', '未知错误')}")
    except Exception as e:
        print(f"❌ 钉钉推送失败: {e}")

def main():
    """主函数，读取最新论文数据并发送钉钉消息"""
    # 获取当前脚本所在目录（paperBotV2/arxiv_daily目录）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_dir = os.path.join(current_dir, "data")
    
    # 获取最新的JSON文件
    latest_json_file = get_latest_json_file(json_dir)
    if not latest_json_file:
        print("无法获取最新的JSON文件，程序退出")
        return
    
    # 从文件名中提取日期并检查是否为今天
    latest_file_name = os.path.basename(latest_json_file)
    if latest_file_name.endswith('.json'):
        file_date_str = latest_file_name[:-5]  # 去掉.json后缀
        try:
            # 解析文件名中的日期
            file_date = datetime.strptime(file_date_str, '%Y%m%d')
            # 获取今天的日期（不含时间）
            today = datetime.now().date()
            # 检查文件日期是否为今天
            if file_date.date() != today:
                print(f"⚠️ 最新文件的日期 {file_date.date()} 不是今天 {today}，避免重复发送，程序退出")
                return
        except ValueError:
            print(f"⚠️ 无法从文件名 {latest_file_name} 中解析日期，继续处理")
    
    # 加载论文数据
    papers = load_paper_data(latest_json_file)
    if not papers:
        print("未加载到论文数据，程序退出")
        return
    
    # 按照精排分数排序并选择前N篇论文
    papers_with_score = [p for p in papers if 'rerank_relevance_score' in p and p.get('is_fine_ranked', False)]
    papers_with_score.sort(key=lambda x: x['rerank_relevance_score'], reverse=True)
    selected_papers = papers_with_score[:RETURN_PAPERS]
    
    # 检查是否有有效的钉钉配置
    if not DINGTALK_ACCESS_TOKEN or not DINGTALK_SECRET:
        print("⚠️ 环境变量 DINGTALK_ACCESS_TOKEN 或 DINGTALK_SECRET 未设置，无法发送钉钉消息")
        return
        
    print(f"📤 准备发送 {len(selected_papers)} 篇论文到钉钉...")
    
    # 发送到钉钉
    if selected_papers:
        send_papers_to_dingding(selected_papers)
    else:
        print("⚠️ 没有符合条件的论文可以发送")

if __name__ == "__main__":
    main()
