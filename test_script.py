# test_script.py
def calculate_total(items):
    total = 0
    for i in range(len(items)):
        total = total + items[i]
    return total

def getUserData(user_id):
    # TODO: Implement database lookup
    if user_id == None:
        return None
    return {"id": user_id, "status": "active"}
