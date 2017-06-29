import site
site.addsitedir('./lib')

import logging
import os
import codecs, difflib, json
from random import randint

from flask import Flask, render_template
from flask_ask import Ask, request, session, question, statement


app = Flask(__name__)
ask = Ask(app, "/")
logging.getLogger('flask_ask').setLevel(logging.DEBUG)
leadership_knowledge = json.load(open('speech_assets/leadership_knowledge.json', 'r'))
leadership_quiz = leadership_knowledge['quiz']
leadership_tips = leadership_knowledge['leadership_tips']

def concatenate_text_items(items):
    """
    Merges items into a text string that will sound natural as spoken word

    Args:
        items (list): Items to concatenate

    Returns:
        (str): Natural sounding list of items
    """
    nat_list = ""

    for i, elem in enumerate(items):
        nat_list += elem

        if i < len(items) - 2:
            nat_list += ', '
        elif i == len(items) - 2:
            nat_list += ', and '

    return nat_list


def init_session(session):
    """
    Initializes attributes dict of session with starting values for tips and
    quiz questions.

    Args:
        session (`obj`: Flask-ASK Session): Current Alexa session
    """
    session.attributes['rem_quiz_ques'] = range(len(leadership_quiz))
    session.attributes['rem_tips'] = range(len(leadership_tips))

def init_quiz_state(session, i_quiz):
    """
    Initializes the state of user progress through answering a quiz question
    that can have a single anwser or a list of n answers.

    Args:
        session (`obj`: Flask-ASK Session): Current Alexa session
        i_quiz (int): Index of current quiz question within knowledge
    """
    ques_type = leadership_quiz[i_quiz]['type']

    if ques_type == 'single_part':
        n_responses = 1
    elif ques_type == 'multi_part':
        n_responses = len(leadership_quiz[i_quiz]['answers'])
    else:
        raise ValueError("Unknown question type")

    session.attributes['state'] = {
        'context':'quiz',
        'index':i_quiz,
        'type':ques_type,
        'n_responses':n_responses,
        'responses':[]
    }

def get_tip_from_sess(session):
    try:
        i_tip = randint(0, len(session.attributes['rem_tips']) - 1)
        return session.attributes['rem_tips'].pop(i_tip)
    except ValueError:
        session.attributes['rem_tips'] = range(len(leadership_tips))
        return get_tip_from_sess(session)

def get_quiz_ques_from_sess(session):
    try:
        i_quiz_ques = randint(0, len(session.attributes['rem_quiz_ques']) - 1)
        return session.attributes['rem_quiz_ques'].pop(i_quiz_ques)
    except ValueError:
        session.attributes['rem_quiz_ques'] = range(len(leadership_quiz))
        return get_quiz_ques_from_sess(session)

def prompt_user_for_more_answers(session):
    """
    Takes the user's response and compares it to the answers for the current
    quiz question using difflib.

    Args:
        session (`obj`: Flask-ASK Session): Current Alexa session
    """
    # Get the session state
    state = session.attributes['state']

    # Check the number of missing responses
    n_missing = state['n_responses'] - len(state['responses'])
    if n_missing == 1:
        speech = render_template('need_one_more_answer')
    elif n_missing > 1:
        speech = render_template('need_more_answers', n_missing=n_missing)

    return question(speech).reprompt(speech)

def check_answers(session):
    """
    Takes the user's response and compares it to the answers for the current
    quiz question using difflib.

    Args:
        session (`obj`: Flask-ASK Session): Current Alexa session

    Returns:
        graded (dict): Matching user responses and answers, and missing answers
    """
    # Get the quiz state
    state = session.attributes['state']
    response = state['responses']

    # Track correct answers and missing answers if applicable
    all_correct = True
    graded = {'correct':{}, 'incorrect':[], 'missing':None}

    # Get the correct answers to the question
    i_quiz = state['index']
    known_answers = [elem['value'] for elem in leadership_quiz[i_quiz]['answers']]

    # Check each user response, removing any matching response before checking the next one
    for resp in response:
        matches = difflib.get_close_matches(resp, known_answers, cutoff=0.8)
        if len(matches) > 0:
            # Mark as correct by saving best match
            graded['correct'][resp] = matches[0]

            # Remove match from list of valid answers
            known_answers.remove(matches[0])
        else:
            # Mark as incorrect
            all_correct = False
            graded['incorrect'].append(resp)

    if len(known_answers) > 0:
        graded['missing'] = known_answers

    return all_correct, graded

def process_answers(session):
    """
    Checks correctness of user responses and generates Alexa's response

    Args:
        session (`obj`: Flask-ASK Session): Current Alexa session

    Returns:
        speech_output (str): Alexa speech for user
    """
    all_correct, graded = check_answers(session)
    if all_correct:
        return "Great job! That is correct."
    else:
        if len(graded['incorrect']) == 1:
            speech_output = render_template('incorrect_answer',
                                            wrong_answer=graded['incorrect'][0],
                                            correct_answer=graded['missing'][0])
        else:
            wrong_answers = concatenate_text_items(graded['incorrect'])
            correct_answers = concatenate_text_items(graded['correct'])
            speech_output = render_template('incorrect_answers',
                                            wrong_answers=wrong_answers,
                                            correct_answers=correct_answers)

        return speech_output

def manage_quiz_state(answers):
    """
    Takes the supplied answers and determines the next steps for the quiz
        -Prompt user to supply answers
        -Check user's answers for correctness

    Args:
        answers (list): Answers supplied by the user
    """
    # Get quiz state
    state = session.attributes['state']

    # Add new answer to list of responses
    state['responses'].extend(answers)

    # Check if the user has supplied all of the answers
    if len(state['responses']) == state['n_responses']:
        # We have the expected number of answers, check whether the supplied
        # answers are correct
        speech_output = process_answers(session)
        speech_output += " " + render_template('continue')
        return question(speech_output).reprompt(speech_output)
    else:
        # Prompt user for additional answers
        return prompt_user_for_more_answers(session)


@ask.launch
def launch():
    init_session(session)
    speech_output = 'Do you want a leadership tip or to play the quiz?'
    reprompt_text = 'With Great Leader, you can get leadership tips to expand your knowledge of leadership or you can test your current knowledge by playing the quiz'
    return question(speech_output).reprompt(reprompt_text)


@ask.intent('GetNewTipIntent')
def get_new_tip():
    session.attributes['state'] = {'context':'tip'}
    i_tip = get_tip_from_sess(session)
    tip = leadership_tips[i_tip]
    fact_text = tip
    card_title = render_template('card_title')
    res = "Would you like another fact or the quiz?"
    return question(fact_text + ". " + res).reprompt(res).simple_card(card_title, fact_text)

@ask.intent('PlayQuizIntent')
def play_quiz():
    i_quiz = get_quiz_ques_from_sess(session)
    init_quiz_state(session, i_quiz)
    quiz_ques = leadership_quiz[i_quiz]['question']
    return question(quiz_ques).reprompt(quiz_ques)

@ask.intent('SingleAnswerIntent')
def single_answer(answer):
    return manage_quiz_state([answer])

@ask.intent('TwoAnswerIntent')
def two_answer(answer_one, answer_two):
    return manage_quiz_state([answer_one, answer_two])

@ask.intent("FiveAnswerIntent")
def five_answer(answer_one, answer_two, answer_three, answer_four, answer_five):
    answers = [answer_one, answer_two, answer_three, answer_four, answer_five]
    return manage_quiz_state(answers)

@ask.intent('AMAZON.HelpIntent')
def help():
    help_text = render_template('help')
    return question(help_text).reprompt(help_text)


@ask.intent('AMAZON.StopIntent')
def stop():
    bye_text = render_template('bye')
    return statement(bye_text)


@ask.intent('AMAZON.CancelIntent')
def cancel():
    bye_text = render_template('bye')
    return statement(bye_text)


@ask.session_ended
def session_ended():
    return "{}", 200


if __name__ == '__main__':
    if 'ASK_VERIFY_REQUESTS' in os.environ:
        verify = str(os.environ.get('ASK_VERIFY_REQUESTS', '')).lower()
        if verify == 'false':
            app.config['ASK_VERIFY_REQUESTS'] = False
    app.run(debug=True)
