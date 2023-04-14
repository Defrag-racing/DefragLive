import os
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
    return re.sub(r'\^(X.{6}|.)', '', value)

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
    pass2 = re.sub(r'[^a-zA-Z0-9!\| ]', '', pass1)
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
    if type(data) != dict:
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
            data['content'] = filter_message(data['content'])

    return data


# https://stackoverflow.com/questions/68731323/replace-numbers-with-letters-and-offer-all-permutations
def replace_special_chars(msg):
    all_items = [SPECIAL_NUMBERS.get(char, [char]) for char in msg]
    return [''.join(elem) for elem in itertools.product(*all_items)]

def filter_numbers_in_message(msg):
    parts = msg.split(' ')

    for idx, part in enumerate(parts):
        msg_stripped = re.sub(r'[^a-zA-Z ]', '', part)
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


def filter_author(author, replace_with='^7UnnamedPlayer'):
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