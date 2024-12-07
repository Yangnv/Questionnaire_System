import os

def count_lines(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return len(f.readlines())

def get_files_by_extension(directory, extensions):
    """获取指定目录下特定扩展名的所有文件"""
    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if any(filename.endswith(ext) for ext in extensions):
                files.append(os.path.join(root, filename))
    return files

# 要统计的文件扩展名
extensions = ['.py', '.html', '.css']

# 获取所有相关文件
all_files = get_files_by_extension('.', extensions)

# 按文件类型分组统计
stats = {}
total = 0

print("\n=== 代码行数统计 ===")
for file in sorted(all_files):
    try:
        lines = count_lines(file)
        ext = os.path.splitext(file)[1]
        
        # 更新统计信息
        if ext not in stats:
            stats[ext] = {'count': 0, 'lines': 0}
        stats[ext]['count'] += 1
        stats[ext]['lines'] += lines
        
        total += lines
        print(f"{file}: {lines} 行")
    except Exception as e:
        print(f"无法读取 {file}: {str(e)}")

# 打印汇总信息
print("\n=== 汇总统计 ===")
for ext, data in stats.items():
    print(f"{ext} 文件: {data['count']} 个, 共 {data['lines']} 行")

print("-" * 20)
print(f"总计: {total} 行") 