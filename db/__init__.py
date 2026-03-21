from db.session import Base, engine


def init_db():
    """初始化数据库，创建所有表"""
    import db.models  # noqa: F401 - 确保所有模型被注册
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("数据库初始化完成")
