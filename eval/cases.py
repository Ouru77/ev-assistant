"""
Labeled eval cases for the LLM action-tag benchmark.

Every phrase here is deliberately phrased so the deterministic router does NOT
catch it — it falls through to the model. We then check whether the model emits
the expected [ACTION:...] tag.

We only test the actions the router never emits itself (SEARCH / NEWS / SCREEN)
plus negatives (ordinary chat that must NOT produce any action). That keeps every
label unambiguous and the score honest.

expected = the action type the model should emit, or None for "no action".
"""

CASES = {
    "en": [
        # --- SEARCH: explicit search / live info the model can't know ---
        ("search the web for the best budget mechanical keyboards", "SEARCH"),
        ("look up who won the champions league final last night", "SEARCH"),
        ("can you find the latest reviews of the framework laptop", "SEARCH"),
        ("what's the current bitcoin price", "SEARCH"),
        ("google the release date of the next pixel phone", "SEARCH"),
        ("look up today's euro to dollar exchange rate", "SEARCH"),

        # --- NEWS ---
        ("what's in the news today", "NEWS"),
        ("give me today's headlines", "NEWS"),
        ("catch me up on the news", "NEWS"),
        ("any big news this morning", "NEWS"),

        # --- SCREEN ---
        ("what's on my screen right now", "SCREEN"),
        ("look at my screen and tell me what you see", "SCREEN"),
        ("can you see what i have open", "SCREEN"),
        ("describe what's on my display", "SCREEN"),

        # --- Negatives: answer from knowledge, NO action tag ---
        ("what's the capital of france", None),
        ("how are you doing today", None),
        ("tell me a short joke", None),
        ("explain what a black hole is in one sentence", None),
        ("what is 15 percent of 240", None),
        ("who wrote the book 1984", None),
        ("give me a quick pasta idea", None),
        ("what's your name", None),
    ],
    "tr": [
        # --- SEARCH ---
        ("internette en iyi bütçe dostu mekanik klavyeleri araştır", "SEARCH"),
        ("dün geceki şampiyonlar ligi finalini kim kazandı araştır", "SEARCH"),
        ("bitcoin'in şu anki fiyatına internetten bak", "SEARCH"),
        ("yeni pixel telefonun çıkış tarihini araştır", "SEARCH"),
        ("euro'nun bugünkü dolar kurunu bul", "SEARCH"),
        ("framework laptop'un son incelemelerini araştır", "SEARCH"),

        # --- NEWS ---
        ("bugün haberlerde ne var", "NEWS"),
        ("günün manşetlerini ver", "NEWS"),
        ("beni haberlerle güncelle", "NEWS"),
        ("bu sabah önemli bir haber var mı", "NEWS"),

        # --- SCREEN ---
        ("şu an ekranımda ne var", "SCREEN"),
        ("ekranıma bak ve ne gördüğünü söyle", "SCREEN"),
        ("açık olan şeyleri görebiliyor musun", "SCREEN"),
        ("ekranımda ne olduğunu betimle", "SCREEN"),

        # --- Negatives ---
        ("fransa'nın başkenti neresi", None),
        ("bugün nasılsın", None),
        ("kısa bir şaka yap", None),
        ("kara delik nedir tek cümleyle anlat", None),
        ("240'ın yüzde 15'i kaç", None),
        ("1984 kitabını kim yazdı", None),
        ("hızlı bir makarna fikri ver", None),
        ("senin adın ne", None),
    ],
}
