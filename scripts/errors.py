import os

ERROR_FILTERS = [
    "ERROR: CL_ParseServerMessage:",
    "Exception Address:",
    "Signal caught (11)",
    "Incorrect challenge, please reconnect",
    "ERROR: CL_ParseServerMessage: read past end of server message",
    "^0^7D^6e^7Frag^6.^7TV^0/^7 was kicked"
]

REPEATING_ERRORS = {}

def calculate_repeating(errors):
    global REPEATING_ERRORS

    for error in errors:
        error_data = error["error"].replace('\n', '')
        if error_data in REPEATING_ERRORS:
            REPEATING_ERRORS[error_data] += 1
        else:
            REPEATING_ERRORS[error_data] = 1

    print("\nRepeating errors:")
    for error in REPEATING_ERRORS:
        print(f"\t{error}: {REPEATING_ERRORS[error]}")

def parse_error(line):
    time = line.split(" ")[1]

    error = line.split("[Q3] ")[1]

    return {
        "time": time,
        "error": error
    }

def get_errors(data):
    errors = []
    for line in data:
        for error in ERROR_FILTERS:
            if error in line and '[Q3]' in line:
                errors.append(parse_error(line))

    return errors

def get_data(file):
    with open(file, "r") as f:
        lines = f.readlines()

    return lines

def get_date_from_filename(filename):
    filename = filename.replace("../logs/", "")
    date = filename.split("_")[0]
    return date

def main(file):
    date = get_date_from_filename(file)
    data = get_data(file)
    errors = get_errors(data)

    print(f"Errors on {date}:")
    for error in errors:
        print(f"\t{error['time']} - {error['error']}")

    calculate_repeating(errors)

if __name__ == "__main__":
    for file in os.listdir("../logs"):
        if file.endswith(".log"):
            main(f"../logs/{file}")
