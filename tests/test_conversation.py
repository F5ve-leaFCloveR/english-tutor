import json
from unittest.mock import MagicMock
import pytest


def test_chat_turn_returns_reply_and_corrections():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({
        "reply": "That's interesting! What kind of book?",
        "corrections": [
            {
                "tag": "grammar",
                "user_utterance": "I readed a book",
                "corrected_version": "I read a book",
                "explanation": "Past tense of 'read' is irregular; same spelling, different pronunciation."
            }
        ],
    })
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="I readed a book yesterday")
    assert res.reply == "That's interesting! What kind of book?"
    assert len(res.corrections) == 1
    assert res.corrections[0].tag == "grammar"
    assert res.corrections[0].corrected_version == "I read a book"


def test_chat_turn_caps_corrections_at_three():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({
        "reply": "ok",
        "corrections": [
            {"tag": "vocab", "user_utterance": "u1", "corrected_version": "c1", "explanation": "e1"},
            {"tag": "vocab", "user_utterance": "u2", "corrected_version": "c2", "explanation": "e2"},
            {"tag": "vocab", "user_utterance": "u3", "corrected_version": "c3", "explanation": "e3"},
            {"tag": "vocab", "user_utterance": "u4", "corrected_version": "c4", "explanation": "e4"},
            {"tag": "vocab", "user_utterance": "u5", "corrected_version": "c5", "explanation": "e5"},
        ],
    })
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert len(res.corrections) == 3


def test_chat_turn_empty_corrections_ok():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"reply": "Cool!", "corrections": []})
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="Hello there.")
    assert res.reply == "Cool!"
    assert res.corrections == []


def test_chat_turn_retries_on_invalid_json_then_succeeds():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.side_effect = [
        "Sorry, here's my answer: " + "not json",
        json.dumps({"reply": "ok", "corrections": []}),
    ]
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert res.reply == "ok"
    assert llm.complete.call_count == 2


def test_chat_turn_returns_fallback_after_two_failures():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = "still not json"
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert res.reply  # non-empty fallback string
    assert res.corrections == []


def test_chat_turn_strips_code_fences():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = "```json\n" + json.dumps({"reply": "hi", "corrections": []}) + "\n```"
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert res.reply == "hi"


def test_chat_turn_includes_history_in_llm_call():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    chat = ChatTurn(llm=llm, model="m")
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How are you?"},
    ]
    chat.respond(history=history, message="I am fine")

    call_kwargs = llm.complete.call_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "Hello"}
    assert messages[2] == {"role": "assistant", "content": "Hi! How are you?"}
    assert messages[-1] == {"role": "user", "content": "I am fine"}
