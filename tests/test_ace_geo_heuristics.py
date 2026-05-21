"""ACE Pro (аська) и гео-запросы в чате."""

from __future__ import annotations



from app.bot.text_heuristics import (

    _has_geo_social_cues,

    _is_geo_social_only_request,

    _topic_is_ace_not_detected_intent,

    _user_already_replaced_motherboard,

)

from app.bot.wiki_ranking import (

    _ace_connection_guide_url_plausible,

    _response_wiki_url_acceptable,

    _topic_path_bonus,

)

from app.ru_layer import expand_queries





_ACE_MSG = (

    "Всем привет. принтер не видит аську. Китайцы прислали usb hub и материнку. "

    "Поменял, по прежнему принтер не видит аську. "

    "кто-нибудь из владельцев Кобра S1 combo живет рядом с Обнинском. "

    "Хочу аську на другой принтер повесить — видится ли она?"

)





def test_ace_not_detected_intent():

    assert _topic_is_ace_not_detected_intent(_ACE_MSG)

    assert _user_already_replaced_motherboard(_ACE_MSG)





def test_geo_with_ace_is_not_geo_only():

    assert _has_geo_social_cues(_ACE_MSG)

    assert not _is_geo_social_only_request(_ACE_MSG)





def test_geo_only_skipped():

    text = "Кто из владельцев Kobra S1 combo живёт рядом с Обнинском?"

    assert _is_geo_social_only_request(text)





def test_expand_queries_adds_ace_binding():

    variants = expand_queries("принтер не видит аську kobra s1 combo")

    assert any("ACE Pro" in v or "binding" in v for v in variants)





def test_motherboard_replacement_rejected_after_swap():

    url = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/motherboard-replacement-guide"

    assert not _response_wiki_url_acceptable(_ACE_MSG, url)





def test_binding_acceptable_for_ace():

    url = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/printer-binding-guide"

    assert _response_wiki_url_acceptable(_ACE_MSG, url)

    assert _ace_connection_guide_url_plausible(url)





def test_binding_bonus_beats_motherboard_penalty():

    bind = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/printer-binding-guide"

    mobo = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/motherboard-replacement-guide"

    b_bind = _topic_path_bonus(_ACE_MSG, bind)

    b_mobo = _topic_path_bonus(_ACE_MSG, mobo)

    assert b_bind > b_mobo



_ACE_CONN_MSG = (

    "пока что только в ACE PRo. на принтер даже почему то не думал, но видимо, "

    "неисправность со стороны принтера. этому предшествовали ошибки и выбрасывание из печати "

    "(но именно когда аська подключена была), говорящие о неисправности в подключении."

)





def test_ace_connection_intent_not_blocking_page():

    from app.bot.text_heuristics import _topic_is_ace_connection_intent, _topic_is_ace_not_detected_intent



    assert _topic_is_ace_connection_intent(_ACE_CONN_MSG)

    assert not _topic_is_ace_not_detected_intent(_ACE_CONN_MSG)

    blocking = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/ace-pro-blocking"

    binding = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/printer-binding-guide"

    network = (

        "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/"

        "network-connection-guide-and-troubleshooting"

    )

    assert not _response_wiki_url_acceptable(_ACE_CONN_MSG, blocking)

    assert _response_wiki_url_acceptable(_ACE_CONN_MSG, binding)

    assert _response_wiki_url_acceptable(_ACE_CONN_MSG, network)

    assert _topic_path_bonus(_ACE_CONN_MSG, binding) > _topic_path_bonus(_ACE_CONN_MSG, blocking)



