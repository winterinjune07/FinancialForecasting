def Float(str):
    try:
        float(str)
        return float(str)
    except ValueError:
        return False

def Int(str):
    try:
        int(str)
        return int(str)
    except ValueError:
        return False

def Bool(str):
    try:
        bool(str)
        return bool(str)
    except ValueError:
        return False

def Date(str):
    from datetime import datetime
    try:
        datetime.strptime(str, '%Y-%m-%d').date()
        return (datetime.strptime(str, '%Y-%m-%d').date())
    except ValueError:
        return False
