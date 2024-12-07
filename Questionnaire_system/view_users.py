# 方法1: 使用 sqlite3 模块直接查询
import sqlite3

def view_users_sqlite():
    # 连接到数据库
    conn = sqlite3.connect('instance/survey.db')
    cursor = conn.cursor()
    
    # 执行查询
    cursor.execute('SELECT id, username, role, student_id, real_name FROM user')
    users = cursor.fetchall()
    
    # 打印用户信息
    print("\n=== 用户列表 ===")
    print("ID | 用户名 | 角色 | 学号 | 真实姓名")
    print("-" * 50)
    for user in users:
        print(f"{user[0]} | {user[1]} | {user[2]} | {user[3] or 'N/A'} | {user[4] or 'N/A'}")
    
    # 关闭连接
    conn.close()

# 方法2: 使用 Flask-SQLAlchemy 模型查询
from app import app, User, db

def view_users_sqlalchemy():
    with app.app_context():
        users = User.query.all()
        
        print("\n=== 用户列表 ===")
        print("ID | 用户名 | 角色 | 学号 | 真实姓名")
        print("-" * 50)
        for user in users:
            print(f"{user.id} | {user.username} | {user.role} | {user.student_id or 'N/A'} | {user.real_name or 'N/A'}")

if __name__ == '__main__':
    # 使��方法1或方法2
    view_users_sqlite()
    # view_users_sqlalchemy() 