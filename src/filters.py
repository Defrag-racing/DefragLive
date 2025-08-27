import re
import ahocorasick
import itertools

from config import get_list

authors_automaton = ahocorasick.Automaton()
chat_automaton = ahocorasick.Automaton()

SPECIAL_NUMBERS = {
    '0': ['o'],
    '1': ['i', 'l'],
    '2': ['z'],
    '3': ['e'],
    '4': ['a', 'h'],
    '5': ['s'],
    '6': ['g', 'b'],
    '7': ['t'],
    '8': ['b', 'g'],
    '9': ['g'],
    'l': ['i'],
    '!': ['i', 'l'],
    '|': ['i', 'l']
}


def strip_q3_colors(value):
    # Updated to handle both numeric and alphabetic color codes
    return re.sub(r'\^(X.{6}|[0-9a-z])', '', value)


def extract_color_codes(text):
    """Extract color codes and their positions from text"""
    color_codes = []
    # Updated regex to match both numeric and alphabetic color codes
    color_regex = r'\^[0-9a-z]'
    
    for match in re.finditer(color_regex, text, re.IGNORECASE):
        color_codes.append({
            'code': match.group(0),
            'position': match.start(),
            'length': len(match.group(0))
        })
    
    return color_codes


def rebuild_with_colors(original_text, censored_clean_text):
    """Rebuild censored text with original color codes intact"""
    color_codes = extract_color_codes(original_text)
    clean_original = strip_q3_colors(original_text)
    
    # If no censoring happened, return original
    if clean_original == censored_clean_text:
        return original_text
    
    # Build mapping of positions in clean text to positions in original text
    result = ""
    clean_idx = 0
    orig_idx = 0
    color_idx = 0
    
    while orig_idx < len(original_text) and clean_idx < len(censored_clean_text):
        # Check if there's a color code at current original position
        if (color_idx < len(color_codes) and 
            color_codes[color_idx]['position'] == orig_idx):
            # Add the color code to result
            result += color_codes[color_idx]['code']
            orig_idx += color_codes[color_idx]['length']
            color_idx += 1
        else:
            # Add character from censored text
            result += censored_clean_text[clean_idx]
            clean_idx += 1
            orig_idx += 1
    
    # Add any remaining characters from censored text
    while clean_idx < len(censored_clean_text):
        result += censored_clean_text[clean_idx]
        clean_idx += 1
    
    # Add any remaining color codes at the end
    while color_idx < len(color_codes):
        if color_codes[color_idx]['position'] <= len(original_text):
            result += color_codes[color_idx]['code']
        color_idx += 1
    
    return result


# replaces "w o r d" with "word"
def strip_spaces_after_every_letter(value):
    tokens = value.split(' ')
    start_idx = 0
    prev_was_letter = False
    for idx, tok in enumerate(tokens):
        if tok == '':
            continue
        if len(tok) == 1:
            if prev_was_letter:
                tokens[start_idx] += tok
                tokens[idx] = ''
            else:
                prev_was_letter = True
                start_idx = idx
        else:
            prev_was_letter = False

    return ' '.join(tokens)


def strip_repeated_characters(value):
    result = []
    for x in value:
        if not result or result[-1] != x:
            result.append(x)
    return ''.join(result)


def clean_string(value):
    pass1 = strip_q3_colors(value)
    pass2 = re.sub(r'[^a-zA-Z0-9!\|: ]', '', pass1)
    # pass3 = strip_spaces_after_every_letter(pass2)
    pass4 = strip_repeated_characters(pass2)
    return pass4


def init():
    load_filters()


def load_filters():
    names = get_list('blacklist_names')
    for idx, line in enumerate(names):
        authors_automaton.add_word(line, (idx, line))

    chat = get_list('blacklist_chat')
    for idx, line in enumerate(chat):
        chat_automaton.add_word(line, (idx, line))

    if len(authors_automaton) > 0:
        authors_automaton.make_automaton()
    if len(chat_automaton) > 0:
        chat_automaton.make_automaton()


def filter_line_data(data):
    if type(data) is not dict:
        return data
    if data["type"] not in ["PRINT",
                            "SAY",
                            "ANNOUNCE",
                            "RENAME",
                            "CONNECTED",
                            "DISCONNECTED",
                            "ENTEREDGAME",
                            "JOINEDSPEC",
                            "REACHEDFINISH",
                            "YOURRANK"]:
        return data

    if len(authors_automaton) > 0:
        if 'author' in data and data['author'] is not None:
            data['author'] = filter_author(data['author'])

    if len(chat_automaton) > 0:
        if 'content' in data and data['content'] is not None:
            # Store original content before filtering
            original_content = data['content']
            
            filtered_m = filter_message(data['content'])

            for i in range(1, 5):
                filtered_m = filter_message(filtered_m)

            # If filtering occurred, rebuild with color codes
            clean_original = strip_q3_colors(original_content)
            clean_filtered = strip_q3_colors(filtered_m)
            
            if clean_original != clean_filtered:
                data['content'] = rebuild_with_colors(original_content, clean_filtered)
            else:
                data['content'] = filtered_m

    return data


# https://stackoverflow.com/questions/68731323/replace-numbers-with-letters-and-offer-all-permutations
def replace_special_chars(msg):
    all_items = [SPECIAL_NUMBERS.get(char, [char]) for char in msg]
    return [''.join(elem) for elem in itertools.product(*all_items)]


def filter_numbers_in_message(msg):
    parts = msg.split(' ')

    for idx, part in enumerate(parts):
        msg_stripped = re.sub(r'(?<!\^)\d+|(?<=\^)\d{2,}', '', part)
        msg_lower = msg_stripped.lower()

        blacklisted_words = get_list("blacklist_chat")

        for word in blacklisted_words:
            if word in msg_lower:
                part = msg_lower.replace(word, '*'*len(word))
                parts[idx] = part

    return ' '.join(parts)


def filter_capital_letters_in_message(msg):
    parts = msg.split(' ')

    for idx, part in enumerate(parts):
        msg_stripped = re.sub(r'[^A-Z ]', '', part)
        msg_lower = msg_stripped.lower()

        blacklisted_words = get_list("blacklist_chat")

        for word in blacklisted_words:
            if word in msg_lower:
                part = msg_lower.replace(word, '*'*len(word))
                parts[idx] = part

    return ' '.join(parts)


def filter_message(msg, separator=' ^7> '):
    # Store original message for color code reconstruction
    original_msg = msg
    
    msg = filter_capital_letters_in_message(msg)
    msg = filter_numbers_in_message(msg)

    prefix = ''
    if separator in msg:
        tokens = msg.split(separator, 1)
        prefix = '{}{}'.format(tokens[0], separator)
        msg = tokens[1]

    msg_stripped = clean_string(msg)
    msg_lower = msg_stripped.lower()
    msg_stripped_array = replace_special_chars(msg_lower)
    msg_stripped_special = msg_lower

    for msg_item in msg_stripped_array:
        msg_item = strip_repeated_characters(msg_item.replace(' ', ''))
        naughty_words = list(chat_automaton.iter(msg_item, ignore_white_space=True))
        if len(naughty_words) > 0:
            msg_stripped_special = msg_item
            break

    naughty_words = list(chat_automaton.iter(msg_stripped_special, ignore_white_space=True))
    if len(naughty_words) > 0:
        for end_index, (insert_order, original_value) in naughty_words:
            start_index = end_index - len(original_value) + 1
            #print((start_index, end_index, (insert_order, original_value)))

            msg_stripped = msg_stripped[:start_index] + ('*'*len(original_value)) + msg_stripped[end_index+1:]

        return '{}^2{}'.format(prefix, msg_stripped)

    return '{}{}'.format(prefix, msg)


def filter_author(author, replace_with='UnnamedPlayer'):
    author = filter_capital_letters_in_message(author)
    author = filter_numbers_in_message(author)

    author_stripped = clean_string(author)
    author_lower = author_stripped.lower()
    author_stripped_array = replace_special_chars(author_lower)
    author_stripped_special = author_lower

    for msg_item in author_stripped_array:
        msg_item = strip_repeated_characters(msg_item.replace(' ', ''))
        naughty_words = list(authors_automaton.iter(msg_item, ignore_white_space=True))
        if len(naughty_words) > 0:
            author_stripped_special = msg_item
            break

    naughty_words = list(authors_automaton.iter(author_stripped_special, ignore_white_space=True))
    if len(naughty_words) > 0:
        return replace_with

    return author