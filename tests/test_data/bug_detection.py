# Mutable default arguments
# Bad Examples
def append_to_list(val, my_list=[]):
    my_list.append(val)
    return my_list

def create_user(name, preferences={}):
    preferences['name'] = name
    return preferences

def standard_setup(items=list()):
    return items

# Dynamic code execution
# Bad Examples
def dyn_code_exec():
    exploit_input_1 = "__import__('os').system('echo HACKED')"
    print(f"Evaluating: {exploit_input_1}")

# Bad Examples 
# Late Binding Bug
def late_binding():
    funcs = []
    for i in range(3):
        def bad_closure():
            return i * 2  # References 'i' via late binding
        funcs.append(bad_closure)
    return funcs

# Exception handling
def exception_handling():
    # Case 1: VIOLATION (Bare except swallowing error)
    try:
        result = 1 / 0
    except:
        pass

    # Case 2: VIOLATION (Broad Exception catch swallowing error)
    try:
        import non_existent_module
    except Exception as e:
        print("An error occurred!") 

    # Case 3: SAFE (Specific exception)
    try:
        int("invalid")
    except ValueError:
        pass

    # Case 4: SAFE (Broad exception but re-raised)
    try:
        open("missing_file.txt")
    except Exception:
        logging.error("Failed")
        raise
