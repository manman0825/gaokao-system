import os
import pandas as pd
from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
import traceback

# ==================== 配置部分 ====================
# 使用相对路径（项目根目录下的文件）
db_file_name = 'gaokao_v7.db'
xlsx_source_path = '福建2025年专家版大数据.xlsx'  # 放在项目根目录
txt_guide_path = '填报指南.txt'  # 放在项目根目录

# ==================== 初始化应用 ====================
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_file_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
db = SQLAlchemy(app)

# ==================== 数据模型 ====================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'user' 或 'admin'

class AdmissionRecord(db.Model):
    __tablename__ = 'admission_records'
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(10))
    batch = db.Column(db.String(50))
    category = db.Column(db.String(50))
    college_name = db.Column(db.String(200))
    college_code = db.Column(db.String(50))
    college_info = db.Column(db.Text)
    major_info = db.Column(db.Text)
    major_name = db.Column(db.String(200))
    major_code = db.Column(db.String(50))
    min_score = db.Column(db.Integer)
    tuition = db.Column(db.String(100))
    city = db.Column(db.String(100))

# ==================== 辅助函数 ====================
def build_college_info(row):
    """构建院校信息字符串"""
    parts = []
    if '院校基础信息' in row and pd.notna(row['院校基础信息']):
        parts.append(f"🏫 {row['院校基础信息']}")
    if '硕博信息' in row and pd.notna(row['硕博信息']):
        parts.append(f"🎓 {row['硕博信息']}")
    return " | ".join(parts) if parts else "暂无院校信息"

def build_major_info(row):
    """构建专业信息字符串"""
    parts = []
    if '专业基础信息' in row and pd.notna(row['专业基础信息']):
        parts.append(f"📚 {row['专业基础信息']}")
    if '硕博信息' in row and pd.notna(row['硕博信息']):
        # 提取硕博信息中的学位点
        degree_list = []
        if '硕士' in str(row['硕博信息']):
            degree_list.append("硕士")
        if '博士' in str(row['硕博信息']):
            degree_list.append("博士")
        if degree_list:
            parts.append(f"🎓学位点：{' + '.join(degree_list)}")
    return " | ".join(parts) if parts else "暂无专业信息"

# ==================== 数据导入函数 ====================
def auto_import_data():
    """自动导入Excel数据到数据库"""
    print(f"📂 检查Excel文件: {xlsx_source_path}")
    
    if not os.path.exists(xlsx_source_path):
        print("❌ Excel文件未找到")
        return 0
    
    print("📥 正在读取并导入数据...")
    try:
        # 读取Excel文件
        df = pd.read_excel(xlsx_source_path, header=2, engine='openpyxl')
        count = 0
        
        with app.app_context():
            # 创建数据库表
            db.create_all()
            
            # 清空现有数据（可选）
            # AdmissionRecord.query.delete()
            # db.session.commit()
            
            # 导入数据
            for index, row in df.iterrows():
                try:
                    # 检查必要字段
                    if '院校名称' not in row or pd.isna(row['院校名称']):
                        continue
                    
                    # 构建信息字符串
                    c_info_str = build_college_info(row)
                    m_info_str = build_major_info(row)
                    
                    # 处理最低分
                    min_score_val = None
                    if '最低分1' in row and pd.notna(row['最低分1']):
                        try:
                            min_score_val = int(row['最低分1'])
                        except:
                            pass
                    
                    # 创建记录
                    record = AdmissionRecord(
                        year=str(row.get('年份', '2025')),
                        batch=str(row.get('批次', '')),
                        category=str(row.get('科类', '')),
                        college_name=str(row['院校名称']),
                        college_code=str(row.get('院校代码', '')),
                        college_info=c_info_str,
                        major_info=m_info_str,
                        major_name=str(row.get('专业名称', '')),
                        major_code=str(row.get('专业代码', '')),
                        min_score=min_score_val,
                        tuition=str(row.get('学费', '')),
                        city=str(row.get('城市', ''))
                    )
                    
                    db.session.add(record)
                    count += 1
                    
                    # 每100条提交一次
                    if count % 100 == 0:
                        db.session.commit()
                        
                except Exception as e:
                    print(f"❌ 第{index}行导入失败: {e}")
                    continue
            
            # 提交剩余记录
            db.session.commit()
            print(f"✅ 成功导入 {count} 条记录")
            return count
            
    except Exception as e:
        print(f"❌ 数据导入失败: {e}")
        traceback.print_exc()
        return 0

# ==================== HTML模板函数 ====================
def html(content):
    """生成完整HTML页面"""
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>福建高考志愿填报系统</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
            .header {{ background: #4CAF50; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .nav {{ margin: 10px 0; }}
            .btn {{ display: inline-block; padding: 8px 15px; margin: 5px; background: #2196F3; color: white; text-decoration: none; border-radius: 5px; }}
            .btn:hover {{ background: #0b7dda; }}
            .form-group {{ margin: 15px 0; }}
            label {{ display: block; margin-bottom: 5px; font-weight: bold; }}
            input, select {{ width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }}
            .results {{ margin-top: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .error {{ color: red; padding: 10px; background: #ffe6e6; border-radius: 5px; }}
            .success {{ color: green; padding: 10px; background: #e6ffe6; border-radius: 5px; }}
            .guide-container {{ line-height: 1.6; }}
            .guide-container h2 {{ color: #2196F3; border-bottom: 2px solid #2196F3; padding-bottom: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎓 福建高考志愿填报系统</h1>
                <div class="nav">
                    <a href="/" class="btn">🏠 首页</a>
                    <a href="/user/dashboard" class="btn">🔍 专业查询</a>
                    <a href="/guide" class="btn">📖 填报指南</a>
                    <a href="/admin" class="btn">⚙️ 管理后台</a>
                </div>
            </div>
            {content}
        </div>
    </body>
    </html>
    '''

# ==================== 路由定义 ====================
@app.route('/')
def index():
    """首页"""
    return html('''
        <h2>欢迎使用福建高考志愿填报系统</h2>
        <p>本系统提供福建省2025年高考招生数据查询服务</p>
        <div style="margin: 20px 0;">
            <a href="/user/login" class="btn">👤 用户登录</a>
            <a href="/admin/login" class="btn">🔑 管理员登录</a>
            <a href="/user/dashboard" class="btn">🔍 直接查询（无需登录）</a>
        </div>
        <div class="success">
            <h3>📊 数据统计</h3>
            <p>• 包含福建省多所高校招生数据</p>
            <p>• 支持按院校、专业、分数等多维度查询</p>
            <p>• 提供详细的院校和专业信息</p>
        </div>
    ''')

@app.route('/user/login', methods=['GET', 'POST'])
def user_login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 简单验证（实际应用中应使用加密和数据库验证）
        if username and password:
            session['username'] = username
            session['role'] = 'user'
            return redirect('/user/dashboard')
        else:
            return html('<div class="error">请输入用户名和密码</div>')
    
    return html('''
        <h2>用户登录</h2>
        <form method="POST">
            <div class="form-group">
                <label>用户名：</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>密码：</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">登录</button>
            <a href="/user/dashboard" class="btn">跳过登录直接查询</a>
        </form>
    ''')

@app.route('/user/dashboard', methods=['GET', 'POST'])
def user_dashboard():
    """用户查询界面"""
    results = []
    query_executed = False
    
    if request.method == 'POST':
        college_name = request.form.get('college_name', '').strip()
        major_name = request.form.get('major_name', '').strip()
        min_score = request.form.get('min_score', '').strip()
        
        # 构建查询
        query = AdmissionRecord.query
        
        if college_name:
            query = query.filter(AdmissionRecord.college_name.like(f'%{college_name}%'))
        if major_name:
            query = query.filter(AdmissionRecord.major_name.like(f'%{major_name}%'))
        if min_score:
            try:
                score = int(min_score)
                query = query.filter(AdmissionRecord.min_score >= score)
            except:
                pass
        
        results = query.limit(100).all()
        query_executed = True
    
    # 构建结果表格
    results_html = ''
    if results:
        results_html = '<h3>查询结果：</h3><table>'
        results_html += '''
            <tr>
                <th>院校名称</th>
                <th>专业名称</th>
                <th>最低分</th>
                <th>批次</th>
                <th>科类</th>
                <th>学费</th>
                <th>城市</th>
                <th>操作</th>
            </tr>
        '''
        for record in results:
            results_html += f'''
                <tr>
                    <td>{record.college_name}</td>
                    <td>{record.major_name}</td>
                    <td>{record.min_score if record.min_score else 'N/A'}</td>
                    <td>{record.batch}</td>
                    <td>{record.category}</td>
                    <td>{record.tuition}</td>
                    <td>{record.city}</td>
                    <td><a href="/detail/{record.id}" class="btn">详情</a></td>
                </tr>
            '''
        results_html += '</table>'
    elif query_executed:
        results_html = '<div class="error">未找到匹配的记录</div>'
    
    return html(f'''
        <h2>🔍 专业查询</h2>
        <form method="POST">
            <div class="form-group">
                <label>院校名称：</label>
                <input type="text" name="college_name" placeholder="输入院校名称（如：厦门大学）">
            </div>
            <div class="form-group">
                <label>专业名称：</label>
                <input type="text" name="major_name" placeholder="输入专业名称（如：经济学类）">
            </div>
            <div class="form-group">
                <label>最低分数：</label>
                <input type="number" name="min_score" placeholder="输入最低分数（如：600）">
            </div>
            <button type="submit" class="btn">查询</button>
            <a href="/" class="btn">返回首页</a>
        </form>
        {results_html}
    ''')

@app.route('/detail/<int:record_id>')
def detail(record_id):
    """查看详情"""
    record = AdmissionRecord.query.get(record_id)
    if not record:
        return html('<div class="error">记录不存在</div>')
    
    return html(f'''
        <h2>📋 详细信息</h2>
        <div style="background: #f9f9f9; padding: 15px; border-radius: 5px;">
            <h3>{record.college_name} - {record.major_name}</h3>
            <p><strong>年份：</strong>{record.year}</p>
            <p><strong>批次：</strong>{record.batch}</p>
            <p><strong>科类：</strong>{record.category}</p>
            <p><strong>院校代码：</strong>{record.college_code}</p>
            <p><strong>专业代码：</strong>{record.major_code}</p>
            <p><strong>最低分：</strong>{record.min_score if record.min_score else 'N/A'}</p>
            <p><strong>学费：</strong>{record.tuition}</p>
            <p><strong>城市：</strong>{record.city}</p>
            <p><strong>院校信息：</strong>{record.college_info}</p>
            <p><strong>专业信息：</strong>{record.major_info}</p>
        </div>
        <div style="margin-top: 20px;">
            <a href="/user/dashboard" class="btn">返回查询</a>
            <a href="/" class="btn">返回首页</a>
        </div>
    ''')

@app.route('/guide')
def guide():
    """填报指南"""
    try:
        content = ""
        if os.path.exists(txt_guide_path):
            with open(txt_guide_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "⚠️ 未找到填报指南文件"
        
        # 简单格式化
        lines = content.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line.startswith('**') and line.endswith('**'):
                formatted_lines.append(f"<h2>{line[2:-2]}</h2>")
            elif line:
                formatted_lines.append(f"<p>{line}</p>")
            else:
                formatted_lines.append("<br>")
        
        return html(f'''
            <div class="header-nav">
                <h2>📖 志愿填报指南</h2>
                <a href="/user/dashboard" class="btn">返回查询</a>
            </div>
            <div class="guide-container">{''.join(formatted_lines)}</div>
        ''')
    except Exception as e:
        return html(f"<h3>读取指南出错</h3><p>{e}</p>")

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """管理员登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 简单管理员验证（实际应用中应更安全）
        if username == 'admin' and password == 'admin123':
            session['username'] = username
            session['role'] = 'admin'
            return redirect('/admin')
        else:
            return html('<div class="error">管理员账号或密码错误</div>')
    
    return html('''
        <h2>管理员登录</h2>
        <form method="POST">
            <div class="form-group">
                <label>管理员账号：</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>密码：</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn">登录</button>
            <a href="/" class="btn">返回首页</a>
        </form>
    ''')

@app.route('/admin')
def admin_panel():
    """管理后台"""
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    
    # 统计数据
    total_records = AdmissionRecord.query.count()
    total_users = User.query.count()
    
    return html(f'''
        <h2>⚙️ 管理后台</h2>
        <div style="display: flex; gap: 20px; margin: 20px 0;">
            <div style="flex: 1; background: #e3f2fd; padding: 15px; border-radius: 5px;">
                <h3>📊 数据统计</h3>
                <p>招生记录数：{total_records}</p>
                <p>注册用户数：{total_users}</p>
            </div>
            <div style="flex: 1; background: #f3e5f5; padding: 15px; border-radius: 5px;">
                <h3>🛠️ 管理功能</h3>
                <a href="/admin/import" class="btn">📥 导入数据</a>
                <a href="/admin/users" class="btn">👥 用户管理</a>
                <a href="/admin/logout" class="btn">🚪 退出登录</a>
            </div>
        </div>
    ''')

@app.route('/admin/import')
def admin_import():
    """数据导入页面"""
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    
    return html('''
        <h2>📥 数据导入</h2>
        <p>点击下方按钮开始导入Excel数据：</p>
        <form action="/admin/do_import" method="POST">
            <button type="submit" class="btn" onclick="return confirm('确定要导入数据吗？这会覆盖现有数据。')">
                开始导入数据
            </button>
        </form>
        <div style="margin-top: 20px;">
            <a href="/admin" class="btn">返回管理后台</a>
        </div>
    ''')

@app.route('/admin/do_import', methods=['POST'])
def admin_do_import():
    """执行数据导入"""
    if session.get('role') != 'admin':
        return redirect('/admin/login')
    
    count = auto_import_data()
    
    if count > 0:
        message = f'<div class="success">✅ 成功导入 {count} 条记录</div>'
    else:
        message = '<div class="error">❌ 数据导入失败，请检查Excel文件路径</div>'
    
    return html(f'''
        <h2>📥 数据导入结果</h2>
        {message}
        <div style="margin-top: 20px;">
            <a href="/admin" class="btn">返回管理后台</a>
            <a href="/admin/import" class="btn">重新导入</a>
        </div>
    ''')

@app.route('/admin/logout')
def admin_logout():
    """管理员退出登录"""
    session.clear()
    return redirect('/')

# ==================== 初始化数据 ====================
def init_database():
    """初始化数据库和默认用户"""
    with app.app_context():
        # 创建所有表
        db.create_all()
        
        # 创建默认管理员用户（如果不存在）
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(username='admin', password='admin123', role='admin')
            db.session.add(admin_user)
            db.session.commit()
            print("✅ 创建默认管理员账号：admin / admin123")
        
        # 创建默认普通用户（如果不存在）
        user = User.query.filter_by(username='user').first()
        if not user:
            user = User(username='user', password='user123', role='user')
            db.session.add(user)
            db.session.commit()
            print("✅ 创建默认用户账号：user / user123")
        
        print("✅ 数据库初始化完成")

# ==================== 主程序 ====================
if __name__ == '__main__':
    # 初始化数据库
    init_database()
    
    # 检查并导入数据（如果数据库为空）
    with app.app_context():
        count = AdmissionRecord.query.count()
        if count == 0:
            print("📊 数据库为空，开始自动导入数据...")
            auto_import_data()
        else:
            print(f"📊 数据库已有 {count} 条记录")
    
    # 启动Flask应用
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 服务器启动在 http://localhost: {port}")
    print(f"📁 数据文件路径：{xlsx_source_path}")
    app.run(host='0.0.0.0', port=port, debug=True)
