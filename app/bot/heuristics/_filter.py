"""Главные фильтры: geo-запросы, clarify-модель, is_chatter, generic_help."""
from __future__ import annotations

import re

from app.bot.heuristics._base import (
    _has_geo_social_cues,
    _is_error_code_query,
    _printer_mentioned,
)
from app.bot.heuristics._ace import (
    _is_ace_unit_trade_banter,
    _is_ace_unit_price_shopping_chatter,
    _is_combo_ace_marketplace_chat,
    _topic_is_ace_not_detected_intent,
)
from app.bot.heuristics._banter import (
    _COLOQUIAL_KAK_RE,
    _is_ace_chitu_hardware_observation,
    _is_bare_competitor_printer_question,
    _is_bare_rhetorical_context_question,
    _is_casual_advice_in_thread,
    _is_chat_meta_discussion,
    _is_chat_past_incident_recollection,
    _is_colloquial_printer_fragment,
    _is_competitor_showcase_request,
    _is_conversational_skepticism,
    _is_cross_chat_tip_sharing,
    _is_design_feature_car_sarcasm,
    _is_expert_deferral_chatter,
    _is_filament_brand_quality_opinion,
    _is_filament_feed_test_probe,
    _is_filament_testing_plan_sharing,
    _is_filament_tolerance_banter,
    _is_first_days_experience_sharing,
    _is_hardware_vs_settings_dilemma,
    _is_layer_profile_thread_opinion,
    _is_marketplace_promo_message,
    _is_money_worth_banter,
    _is_multicolor_experience_opinion,
    _is_multicolor_preset_banter,
    _is_multicolor_tower_rhetoric,
    _is_offbeat_social_banter,
    _is_other_printer_maintenance_story,
    _is_partial_manual_find_observation,
    _is_peer_action_experience_question,
    _is_peer_claim_debate_relay,
    _is_peer_diagnostic_interrogation,
    _is_peer_social_printer_question,
    _is_personal_chat_action_reference,
    _is_price_hyperbole_banter,
    _is_price_negotiation_chatter,
    _is_print_quality_meta_curiosity,
    _is_print_task_planning_statement,
    _is_printer_comparison_opinion,
    _is_printer_purchase_material_opinion,
    _is_printing_status_announcement,
    _is_problem_combo_banter,
    _is_product_news_announcement,
    _is_purchase_deliberation_banter,
    _is_relay_to_peer_chatter,
    _is_sarcastic_printer_banter,
    _is_sarcastic_thread_banter,
    _is_slicer_app_disambiguation,
    _is_technical_observation_sharing,
    _is_technical_opinion_sharing,
    _is_thread_printing_tip,
    _is_unrelated_pc_hardware_banter,
    _is_vague_filament_thread_reference,
    _message_has_help_intent,
    _is_pure_numeric_or_symbol_message,
    _is_causal_continuation,
    _is_anaphoric_person_question,
    _is_chat_social_moderation,
    _is_profanity_outburst_chatter,
    _is_works_fine_reassurance,
    _is_marketplace_search_chatter,
    _is_peer_diagnostic_checklist,
    _is_bare_combo_variant_fragment,
    _is_social_location_question,
    _is_content_post_request,
    _is_thread_continuation_filler,
    _is_competitor_model_disambiguation,
    _is_slicer_preview_chatter,
    _is_personal_opinion_remark,
    _is_photo_observation_musing,
    _is_bare_fragment_question,
    _is_community_experience_poll,
    _is_private_money_contact_spam,
    _is_firmware_slicer_version_gossip,
    _is_offtopic_news_or_shop_meta,
    _is_thread_humor_meme,
    _is_filament_brand_social_chat,
    _is_general_thread_sidebar,
    _is_peer_calibration_reply_chatter,
    _is_thread_bed_surface_opinion,
    _is_bot_helper_appreciation_meta,
    _is_offtopic_work_life_sidebar,
    _is_offtopic_auto_sidebar,
    _is_figurative_mood_remark,
    _is_ace_meta_banter,
    _is_personal_upholstery_project_sidebar,
    _is_vague_fix_without_symptom,
)
from app.bot.heuristics._intents import (
    _topic_is_marketplace_commerce_intent,
    _topic_needs_printer_model,
)


def _is_geo_social_only_request(text: str) -> bool:
    """
    Координация встреч/обмена с соседями — бот молчит.

    Если в том же сообщении есть тех. проблема (ACE, код ошибки) — ищем вики.

    """
    if not _has_geo_social_cues(text):
        return False
    if _topic_is_ace_not_detected_intent(text) or _is_error_code_query(text):
        return False
    if _topic_needs_printer_model(text) and _printer_mentioned(text):
        return False
    return True


def _needs_model_clarification(text: str) -> bool:
    # Для кодов ошибок модель не спрашиваем — либо найдём страницу по коду, либо промолчим.
    if _is_error_code_query(text):
        return False
    # Наблюдения и бытовой чат — модель не уточняем.
    if _is_non_wiki_chatter_message(text):
        return False
    return _topic_needs_printer_model(text) and not _printer_mentioned(text)


def _is_non_wiki_chatter_message(text: str) -> bool:
    """Сообщения чата, на которые бот не отвечает из вики."""
    return (
        _topic_is_marketplace_commerce_intent(text)
        or _is_relay_to_peer_chatter(text)
        or _is_money_worth_banter(text)
        or _is_design_feature_car_sarcasm(text)
        or _is_peer_claim_debate_relay(text)
        or _is_peer_social_printer_question(text)
        or _is_peer_diagnostic_interrogation(text)
        or _is_peer_action_experience_question(text)
        or _is_filament_feed_test_probe(text)
        or _is_price_negotiation_chatter(text)
        or _is_price_hyperbole_banter(text)
        or _is_combo_ace_marketplace_chat(text)
        or _is_ace_unit_price_shopping_chatter(text)
        or _is_ace_unit_trade_banter(text)
        or _is_printer_purchase_material_opinion(text)
        or _is_filament_brand_quality_opinion(text)
        or _is_filament_tolerance_banter(text)
        or _is_vague_filament_thread_reference(text)
        or _is_bare_competitor_printer_question(text)
        or _is_competitor_showcase_request(text)
        or _is_product_news_announcement(text)
        or _is_printer_comparison_opinion(text)
        or _is_multicolor_experience_opinion(text)
        or _is_printing_status_announcement(text)
        or _is_layer_profile_thread_opinion(text)
        or _is_first_days_experience_sharing(text)
        or _is_conversational_skepticism(text)
        or _is_sarcastic_thread_banter(text)
        or _is_sarcastic_printer_banter(text)
        or _is_slicer_app_disambiguation(text)
        or _is_filament_testing_plan_sharing(text)
        or _is_print_quality_meta_curiosity(text)
        or _is_colloquial_printer_fragment(text)
        or _is_technical_opinion_sharing(text)
        or _is_technical_observation_sharing(text)
        or _is_partial_manual_find_observation(text)
        or _is_cross_chat_tip_sharing(text)
        or _is_ace_chitu_hardware_observation(text)
        or _is_multicolor_preset_banter(text)
        or _is_other_printer_maintenance_story(text)
        or _is_chat_meta_discussion(text)
        or _is_chat_past_incident_recollection(text)
        or _is_thread_printing_tip(text)
        or _is_hardware_vs_settings_dilemma(text)
        or _is_purchase_deliberation_banter(text)
        or _is_problem_combo_banter(text)
        or _is_pure_numeric_or_symbol_message(text)
        or _is_offbeat_social_banter(text)
        or _is_bare_rhetorical_context_question(text)
        or _is_personal_chat_action_reference(text)
        or _is_unrelated_pc_hardware_banter(text)
        or _is_casual_advice_in_thread(text)
        or _is_multicolor_tower_rhetoric(text)
        or _is_geo_social_only_request(text)
        or _is_print_task_planning_statement(text)
        or _is_causal_continuation(text)
        or _is_anaphoric_person_question(text)
        or _is_chat_social_moderation(text)
        or _is_profanity_outburst_chatter(text)
        or _is_works_fine_reassurance(text)
        or _is_marketplace_search_chatter(text)
        or _is_peer_diagnostic_checklist(text)
        or _is_bare_combo_variant_fragment(text)
        or _is_social_location_question(text)
        or _is_content_post_request(text)
        or _is_thread_continuation_filler(text)
        or _is_competitor_model_disambiguation(text)
        or _is_slicer_preview_chatter(text)
        or _is_personal_opinion_remark(text)
        or _is_photo_observation_musing(text)
        or _is_bare_fragment_question(text)
        or _is_community_experience_poll(text)
        or _is_private_money_contact_spam(text)
        or _is_firmware_slicer_version_gossip(text)
        or _is_offtopic_news_or_shop_meta(text)
        or _is_thread_humor_meme(text)
        or _is_filament_brand_social_chat(text)
        or _is_general_thread_sidebar(text)
        or _is_peer_calibration_reply_chatter(text)
        or _is_thread_bed_surface_opinion(text)
        or _is_bot_helper_appreciation_meta(text)
        or _is_vague_fix_without_symptom(text)
        or _is_offtopic_work_life_sidebar(text)
        or _is_offtopic_auto_sidebar(text)
        or _is_figurative_mood_remark(text)
        or _is_ace_meta_banter(text)
        or _is_personal_upholstery_project_sidebar(text)
    )


def _is_conversational_chatter(text: str) -> bool:
    """Бытовая реплика в чате — не отвечать ссылкой из вики."""
    if not text or not text.strip():
        return False
    if _is_non_wiki_chatter_message(text):
        return True
    if _message_has_help_intent(text):
        return False
    if _is_marketplace_promo_message(text):
        return False
    if _is_expert_deferral_chatter(text):
        return True
    t = re.sub(r"\s+", " ", text.lower()).strip()
    if _is_colloquial_printer_fragment(text):
        return True
    if _COLOQUIAL_KAK_RE.search(t):
        return True
    if re.search(r"\bчто\s*ли\b|\bчтоли\b", t):
        return True
    if re.search(r"\bразберемся\b", t):
        return True
    if re.search(r"\bшумит\b|\bшум\b", t):
        return True
    if re.search(r"\b(?:они|у\s+них|тут\s+кстати)\b", t) and re.search(
        r"\b(?:приклеил|приклеили|сделал|сделали|кстати)\b", t
    ):
        return True
    return False


def _is_generic_help_without_context(text: str) -> bool:
    """
    "помогите/спасите" без конкретики — лучше попросить уточнение, а не искать по вики наугад.

    """
    t = (text or "").lower()
    # «помогите» в цитате про прошлый чат — не просьба к боту.
    if _is_chat_meta_discussion(text):
        return False
    if not any(k in t for k in ("помогите", "спасите", "help", "памагити", "спаситипамагити")):
        return False
    # если есть код ошибки или модель/принтер или тех. тема — это уже конкретика
    if _is_error_code_query(text) or _printer_mentioned(text) or _topic_needs_printer_model(text):
        return False
    return True
