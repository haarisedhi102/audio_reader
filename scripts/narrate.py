import re, sys, json, os, unicodedata

# ---------- pronunciation lexicon (applied to narration text only) ----------
LEX = {
    # Turkish / Ottoman terms, doc 1
    "Okçular Tekkesi": "Okchular Tekkessy",
    "Okçular tekkesi": "Okchular tekkessy",
    "Okmeydanı": "Okmaydunu",
    "okmeydanı": "okmaydunu",
    "Özveri": "Uzvery",
    "Kâtip": "Khahtip",
    "Katip": "Khahtip",
    "Kâtibi": "Khahtiby",
    "Sefâret": "Sefahret",
    "menzil taşı": "menzil tashuh",
    "menzil taşları": "menzil tashluruh",
    "nişan taşı": "nishan tashuh",
    "Dikili taşı": "Dikili tashuh",
    "taşı": "tashuh",
    "taşları": "tashluruh",
    "Büyük Kabza Alma Töreni": "Boo-yook Kabza Alma Tur-enny",
    "Tirendâz": "Teerendahz",
    "Osmanlıca": "Osmanlujuh",
    "kabza sahibi": "kabza sahibi",
    "Kavaidi’r-Remy": "Kavaid ir Remy",
    "Tunç Beyhan": "Toonch Bayhan",
    "Gürsoy": "Gurrsoy",
    "Topkapı": "Topkapuh",
    "zeytûnî temren": "zaytoony temren",
    "zeytûnî": "zaytoony",
    "Löwenhielm": "Lurvenhielm",
    "Tirà l'arc": "Tee-rah lar",
    "ancêtres": "ahnsaitruh",
    "Cécile": "Sayseel",
    "pishrev": "pishrev",
    "azmayeesh": "azmayesh",
    "soya": "soya",
    "gez": "gez",
    "sufis": "soofees",
    "Kipchak": "Kipchak",
    "Osmanlıca": "Osmanlujuh",
    # Turkish / Arabic terms, doc 2 (extended below after extraction)
}


LEX.update({
    "Şeyh": "Shaykh", "Şeyh’s": "Shaykh’s", "Yesārīzāde": "Yesarizadeh",
    "Yesarîzade": "Yesarizadeh", "al-Yesārī": "al-Yesari",
    "Hamdullah": "Humdullah", "Necmeddin": "Nejmeddin", "Okyay": "Okyai",
    "Ayanoğlu": "Ayanolu", "Nişantaşı": "Nishtanshi", "Kubbealtı": "Kubbealti",
    "Kuşoğlu": "Kusholu", "Yıldırım": "Yildirim", "İsmail": "Ismail",
    "İbrahim": "Ibrahim", "İnal": "Inal", "İsfendiyar": "Isfendiyar",
    "Konyalı": "Konyali", "Kasım": "Kasim", "Hakkı": "Hakki", "Fazıl": "Fazil",
    "Hacı": "Haji", "Uğur": "Uur", "Şişli": "Shishli", "Teşvikiye": "Teshvikiye",
    "Unkapanı": "Unkapani", "Meydanı": "Meydani", "nişan": "nishan",
    "meşk": "meshk", "tuğra": "tughra", "tuğras": "tughras", "tuğra-keş": "tughrakesh",
    "kemankeş": "kemankesh", "kemankeşlik": "kemankeshlik", "kemān-ı": "keman-i",
    "keşide": "keshideh", "tevki": "tawqi", "tawqīʿ": "tawqi", "riqāʿ": "riqa",
    "taʿlīq": "taleeq", "ta'līq": "taleeq", "ta’lik": "taleeq", "talik": "taleeq",
    "jalī": "jali", "sülüs": "sulus", "celî": "jali", "khattāt": "khattat",
    "Hülâsa": "Hulasah", "kavsnāme": "kavsnameh", "kavs-i": "kavsi",
    "Arabî": "Arabi", "Remy": "Remy", "İlm-i": "Ilm-i",
    "Büyük": "Booyook", "Töreni": "Turenny", "Osmanlıca": "Osmanlujah",
    "şast": "shast", "zihgir": "zihgeer", "zeytûnî": "zaytoony",
    "temeşşuk": "temeshshuk", "usûl": "usul", "âdâb": "adab",
    "istif": "istif", "teşbih": "teshbih", "tefriş": "tefrish",
    "ma'kūs": "makus", "manshūr": "manshur", "matbūʿ": "matbu",
    "midād": "midad", "ijāza": "ijaza", "kifāya": "kifaya",
    "Bâyezid": "Bayezid", "Mahmûd": "Mahmud", "Mansûr": "Mansur",
    "Celâleddin": "Jalaluddin", "Mevlâna": "Mevlana", "Nakşidil": "Nakshidil",
    "Maraşî": "Marashi", "Besyûni": "Basyuni", "Şerif": "Sherif",
    "Kâğıthane": "Kaghithane", "Eyyûb": "Eyyub", "Eyüb": "Eyub", "Eyüp": "Eyup",
    "Medresetü’l-Hattatîn": "Medreset-ul Hattatin",
    "Medresetü’l-Hattâtîn": "Medreset-ul Hattatin",
    "Medrestü’l-Hattatîn’e": "Medreset-ul Hattatine",
    "Dâru’l-İhyâu’s-Sünneti’n-Nebeviyye": "Dar-ul Ihya-us Sunnat-in Nabaviyya",
    "Ashabi’n-Nebî": "Ashab-in Nabi", "Nihayetü’l-Ereb": "Nihayat-ul Ereb",
    "Fünûni’l-Edep": "Funun-il Edeb", "Ebu’l-Hüseyn": "Abul Husayn",
    "Ebu’l-Kasım": "Abul Kasim", "Abdülhamid": "Abdulhamid",
    "Abdulhamîd": "Abdulhamid", "Abdülaziz’s": "Abdulaziz’s",
    "Abdülmecid": "Abdulmejid", "Abdi’l-Latîf": "Abd-il Latif",
    "Kütüb-i": "Kutub-i", "Kânî": "Kani", "Kānī": "Kani", "Kâmil": "Kamil",
    "Kâni": "Kani", "Sa'düddin": "Saduddin", "Reisü’l-Hattatîn": "Reis-ul Hattatin",
    "Hüsn-i": "Husn-i", "Hâfız": "Hafiz", "mīm": "meem", "nūn": "noon",
    "sīn": "seen", "qāf": "qaf", "bāʾ": "ba", "tuğrakeş": "tughrakesh",
    "levhaları": "levhalari", "yazılı": "yazili", "yatağı": "yataghi",
    "otağ-ı": "otagh-i", "saādet": "saadet", "saʿādet": "saadet",
    "Peygamberī": "Payghambari", "Rasāʾilāt-i": "Rasailat-i",
    "Resâilât-ı": "Resailat-i", "beyne’s-sutūr": "bayn-as sutur",
    "wa-aʿiddū": "wa a iddu", "wa-lākinna": "wa lakinna", "wa-mā": "wa ma",
    "bi’llāh": "billah", "ilāha": "ilaha", "illā": "illa", "lā": "la",
    "aʿtum": "a tum", "beşşere": "bashshara", "balağa-i": "balagha-i",
    "aşere-i": "ashara-i", "al-ʿashara": "al-ashara", "ʿashara": "ashara",
    "Qur’an": "Quran", "Qur’anic": "Quranic", "al-Qur’an": "al-Quran",
    "Jihād": "jihad", "al-Jihād": "al-jihad", "Sūrat": "Surat", "sūras": "suras",
    "al-Anfāl": "al-Anfal", "al-Anʿām": "al-Anam", "al-Bayhaqī": "al-Bayhaqi",
    "al-Bukhārī": "al-Bukhari", "Bukhārī": "Bukhari", "al-Daylamī": "al-Daylami",
    "al-Dunyā": "al-Dunya", "al-Lakhmī": "al-Lakhmi", "al-Nabaʾ": "al-Naba",
    "al-Nabī": "al-Nabi", "al-Nasāʾī": "al-Nasai", "Nasāʾī": "Nasai",
    "al-Nuwayrī’s": "al-Nuwayri’s", "al-Suyū": "al-Suyu", "Suyūṭī": "Suyuti",
    "al-Sāʿidī": "al-Saidi", "al-Tirmidhī": "al-Tirmidhi",
    "al-Mustaʿ": "al-Musta", "al-ʿAlaq": "al-Alaq", "Anbiyāʾ": "Anbiya",
    "Masājid": "Masajid", "Mawāqīt": "Mawaqit", "Mevâkit": "Mawaqit",
    "Mesâcid": "Masajid", "Tafsīr": "Tafseer", "Miʿrāj": "Miraj",
    "Imāra": "Imara", "Dāwūd": "Dawood", "Abū": "Abu", "Abī": "Abi",
    "Mālik": "Malik", "Māja": "Maja", "Yāqūt": "Yakoot", "ʿUqba": "Uqba",
    "ʿĀmir": "Aamir", "Waqqā": "Waqqa", "Saʿd": "Sad", "Sa’d": "Sad",
    "ʿayn": "ayn", "Yā": "Ya", "yā": "ya", "yā-i": "ya-i", "Nūn": "Noon",
    "Allāh": "Allah", "Allāhu": "Allahu", "Allāha": "Allaha", "abū": "abu",
    "kāna": "kana", "qaws-ı": "qaws-i", "qawwās": "qawwas", "ramā": "rama",
    "Rumāt": "Rumat", "Rumât": "Rumat", "zerefşân": "zerefshan",
    "şerif": "sherif", "Şark": "Shark", "Ateş": "Atesh",
    # thesis vocabulary
    "thuluth": "thuluth", "sülüs": "sulus", "nesih": "nesih", "neshi": "neshi",
    "muhakkak": "muhakkak", "reyhânî": "reyhani", "rīḥān": "rehan",
    "tevkî’": "tawqi", "tevkî": "tawqi", "tauqīʿ": "tawqi",
    "rıkâ’": "riqa", "rıkâ": "riqa", "riqāʿ": "riqa", "riq’a": "riqa",
    "kit’a": "kita", "kıt’a": "kita", "kıt’alar": "kitalar", "kıt’aler": "kitaler",
    "kit’alar": "kitalar", "kit’aler": "kitaler", "murakkaa": "murakka",
    "ijāza": "ijaza", "icazet": "ijazet", "tezhip": "tezhip", "levha": "levha",
    "levhalar": "levhalar", "karalama": "karalama", "baraka": "baraka",
    "müfredât": "mufredat", "mürekkebât": "murekkebat", "meşk": "meshk",
    "alaqlām": "al-aqlam", "ḥarakāt": "harakat", "adab": "adab", "adāb": "adab",
    "Çelebi": "Chelebi", "Uğur": "Uur", "Hüseyin": "Huseyin", "Savaş": "Savash",
    "Başar": "Bashar", "Öksüz": "Uksuz", "Özçay": "Uzchay", "Özkafa": "Uzkafa",
    "Kılıç": "Kilich", "Tiriyaki": "Tiriyaki", "Süleyman": "Suleyman",
    "Karahisârî": "Karahisari", "Hâfiz": "Hafiz", "Eyyûbî": "Eyyubi",
    "Derviş": "Dervish", "Suyolcuzâde": "Suyolcuzade", "Mustaʻṣimī": "Mustasimi",
    "Muqla": "Muqla", "Bawwāb": "Bawwab", "Muqtadir": "Muqtadir",
    "Qāhir": "Qahir", "Rāḍī": "Radi", "Birol": "Birol",
    "fana’": "fana", "baqā’": "baqa", "irtiqa’": "irtiqa", "ru’ya": "ruya",
    "wa’l-qalam": "wal qalam", "illa’llah": "illallah", "shaa’llah": "shaallah",
    "jamilun": "jamilun", "hoca": "hoja", "Es’ad": "Esad", "aqa’iq": "aqaiq",
})

DIACRITIC_MAP = {
    "ş":"sh","Ş":"Sh","ç":"ch","Ç":"Ch","ğ":"","Ğ":"","ı":"i","İ":"I",
    "ö":"u","Ö":"U","ü":"u","Ü":"U","â":"a","Â":"A","î":"i","Î":"I",
    "û":"u","Û":"U","ā":"a","Ā":"A","ī":"i","Ī":"I","ū":"u","Ū":"U",
    "ḍ":"d","ṣ":"s","ṭ":"t","ẓ":"z","ḥ":"h","ġ":"g","ṅ":"n",
    "Ḥ":"H","Ṣ":"S","Ṭ":"T","Ẓ":"Z","Ḍ":"D","Ġ":"G",
    "ș":"s","Ș":"S","ț":"t","Ț":"T","Ӧ":"O","ӧ":"o",
    "é":"e","è":"e","ê":"e","É":"E","ë":"e","á":"a","à":"a","ä":"a",
    "í":"i","ó":"o","ú":"u","ñ":"n","ő":"o","ű":"u",
    "ʿ":"","ʾ":"","ʽ":"","ʹ":"",
}

def anglicize(t):
    """Last-resort readability for transliterations the lexicon did not cover."""
    if not any(c in DIACRITIC_MAP for c in t):
        return t
    out = "".join(DIACRITIC_MAP.get(c, c) for c in t)
    out = re.sub(r"(?<=[a-z])h(?=[bcdfghjklmnpqrstvwxz])", "", out)
    return out

def load_shared():
    """Hand-curated lexicon lives in data/lexicon.json so it can grow without
    touching code."""
    try:
        d = json.load(open("/Users/haarisedhi/ocr _to_speech/data/lexicon.json"))
        LEX.update(d.get("terms", {}))
        HOMOPHONES.update(d.get("homophones", {}))
    except FileNotFoundError:
        pass

def load_extra(path):
    try:
        LEX.update(json.load(open(path)))
    except FileNotFoundError:
        pass

# ---------- text normalisation ----------
ORD = {1:"first",2:"second",3:"third",4:"fourth",5:"fifth",6:"sixth",7:"seventh",
       8:"eighth",9:"ninth",10:"tenth",11:"eleventh",12:"twelfth",13:"thirteenth",
       14:"fourteenth",15:"fifteenth",16:"sixteenth",17:"seventeenth",18:"eighteenth",
       19:"nineteenth",20:"twentieth",21:"twenty-first"}

def spoken(t):
    t = t.replace("**","").replace("__","")
    t = re.sub(r"(?<=\s)\*|\*(?=[\s.,;:)”’]|$)", "", t)
    t = re.sub(r"^\*|\*$", "", t)
    t = t.replace("(s.a.v.)", "peace and blessings be upon him")
    t = t.replace("(r.a.)", "may Allah be pleased with him")
    t = t.replace("(a.s.)", "peace be upon him")
    t = re.sub(r"\bb\.\s+", "ibn ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)   # links
    t = re.sub(r"^\s*#+\s*", "", t)
    t = t.replace("Dr.", "Doctor")
    t = t.replace("PhD", "P H D")
    t = t.replace("Prof.", "Professor").replace("Assoc.", "Associate")
    t = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", lambda m: ORD.get(int(m.group(1)), m.group(0)), t)
    t = t.replace("1940s","nineteen forties").replace("1950s","nineteen fifties").replace("60s","sixties")
    t = re.sub(r"\b(\d{2,3})\s*m\b", r"\1 meters", t)
    t = re.sub(r"(\d+)-(\d+)", r"\1 to \2", t)
    t = t.replace("No: 46","number 46").replace("etc.","etcetera.")
    t = t.replace("e.g.","for example").replace("i.e.","that is")
    t = t.replace("distance/(flight)","distance and flight").replace("bow(-grip)","bow grip")
    t = t.replace("Sultan Mehmed II","Sultan Mehmed the Second")
    t = t.replace("Sultan Mahmud II","Sultan Mahmud the Second")
    t = t.replace("Sultan Selim III","Sultan Selim the Third")
    t = t.replace("(Selim III)","(Selim the Third)")
    t = re.sub(r"\s*\(Photos?: [^)]*\)", "", t)
    t = re.sub(r"\s*\(Author’s archive\)", "", t)
    t = t.replace("*", "").replace("|", "").replace("#", "")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()

HOMOPHONES = {
    "bow": "boe", "bows": "boes", "Bow": "Boe", "Bows": "Boes",
    "bowstring": "boestring", "bowstrings": "boestrings",
    "bowyers": "boyers", "bowyer": "boyer", "bowyery": "boyery",
    "bowshot": "boeshot", "bowmen": "boemen", "bowman": "boeman",
    "longbow": "longboe", "longbows": "longboes",
    "crossbow": "crossboe", "crossbows": "crossboes",
}

load_shared()

_REVERSE: dict = {}

def _build_reverse():
    if _REVERSE:
        return
    for term, say in sorted({**HOMOPHONES, **LEX}.items(), key=lambda kv: -len(kv[1])):
        _REVERSE.setdefault(say.lower(), term)

def display_text(t: str) -> str:
    """Undo pronunciation respellings for anything shown on screen."""
    _build_reverse()
    for say, term in sorted(_REVERSE.items(), key=lambda kv: -len(kv[0])):
        if " " in say:
            t = re.sub(r"(?<![\w])" + re.escape(say) + r"(?![\w])", term, t, flags=re.I)
    return re.sub(r"[A-Za-z][A-Za-z']+",
                  lambda m: _REVERSE.get(m.group(0).lower(), m.group(0)), t)

def apply_homophones(t):
    for k, v in HOMOPHONES.items():
        t = re.sub(r"\b" + k + r"\b", v, t)
    return t

def apply_lexicon(t):
    if os.environ.get("TTS_HOMOPHONES", "0") == "1":
        t = apply_homophones(t)
    for k in sorted(LEX, key=len, reverse=True):
        t = re.sub(r"(?<![\w’'])" + re.escape(k) + r"(?![\w’'])", LEX[k], t)
    t = re.sub(r"[A-Za-z\u00C0-\u024F\u1E00-\u1EFF\u02BB\u02BC\u02BE\u02BF]+",
               lambda m: anglicize(m.group(0)), t)
    # drop remaining scripts (Arabic letter samples, stray glyphs) — the prose names them anyway
    t = re.sub(r"[\u0400-\u04FF\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+", " ", t)
    t = re.sub(r"[^\x00-\x7f“”‘’–—…]", "", t)
    return re.sub(r"\s{2,}", " ", t)

def narrate(md_path, out_path, kind):
    lines = open(md_path).read().split("\n")
    blocks, buf = [], []
    skip = False
    for ln in lines:
        s = ln.strip()
        if kind == "academic":
            if re.match(r"^#+\s*Page \d+", s):      # page markers
                continue
            if re.match(r"^#+\s*(Kaynakça|Bibliography|References)\s*$", s, re.I):
                skip = True
            if skip:
                continue
            if re.match(r"^Figure\s+\d+$", s):
                continue
            if re.search(r"ORCID|@|Department of|Faculty of|University,", s):
                continue
            if s.startswith("<!--") or s in ("---", ""):
                if s == "":
                    if buf: blocks.append(" ".join(buf)); buf = []
                continue
        if s.startswith("<!--") or re.fullmatch(r"-{3,}", s):
            continue
        if s == "":
            if buf: blocks.append(" ".join(buf)); buf = []
            continue
        if s.startswith("#"):
            if buf: blocks.append(" ".join(buf)); buf = []
            title = re.sub(r"^#+\s*", "", s)
            m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$", title)
            if m:
                num, rest = m.group(1), m.group(2)
                words = " ".join(ORD.get(int(p), p) if p.isdigit() else p for p in num.split("."))
                blocks.append(f"Section {words}. {rest}")
            else:
                blocks.append(title)
            continue
        buf.append(s)
    if buf: blocks.append(" ".join(buf))

    paras = [apply_lexicon(spoken(b)) for b in blocks]
    paras = [p for p in paras if p]
    open(out_path, "w").write("\n\n".join(paras))

    ai = sum(len(p) for p in paras if any(ord(c) > 127 for c in p))
    print(f"{md_path} -> {out_path}: {len(paras)} blocks, "
          f"{sum(len(p.split()) for p in paras)} words, {len(' '.join(paras))} chars")
    return paras

if __name__ == "__main__":
    if len(sys.argv) > 1:
        load_extra(sys.argv[1])
    narrate("/Users/haarisedhi/ocr _to_speech/A_Turkish_Archer_On_The_Tracks_Of_His_An.md",
            "/Users/haarisedhi/ocr _to_speech/narration_archer.txt", "article")
    narrate("/Users/haarisedhi/ocr _to_speech/Okculuk_ve_Hat_Sanati_EN.md",
            "/Users/haarisedhi/ocr _to_speech/narration_okculuk.txt", "academic")
