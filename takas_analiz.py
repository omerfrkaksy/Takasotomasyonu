#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
takas_analiz.py — Takas işaret aracı.

TEK CSV (T+2 aracı kurum/takas dağılımı) ile çalışır → "şüphe" modu.
İKİ CSV ile (--gunici gün içi dağılım) → "KESİN VİRMAN" modu:
  gün içi NET işlem ile T+2 takas ADET FARK karşılaştırılır.

Kaynak: docs/wiki/OtomasyonKurallari.md (Bölüm A) + takas_otomasyon_spec.md.

ÖNEMLİ: Bu araç "AL/SAT" demez. Yalnızca işaret/şüphe üretir. Karar insana aittir.

Kullanım:
    python3 takas_analiz.py <takas.csv> [--gunici <dagilim.csv>] \
        [--hisse KOD] [--esik 0.01] [--top 15]
"""

import argparse
import csv
import io
import os
import sys
from datetime import datetime

# ------------------------------------------------------------------ #
# Kurum sınıflandırma (Özellik 6)
# ------------------------------------------------------------------ #
YABANCI_SAKLAMA = [
    "CITIBANK", "CITI", "DEUTSCHE", "BANK OF AMERICA", "BOFA", "MERRILL",
    "JP MORGAN", "JPMORGAN", "MORGAN STANLEY", "HSBC", "UBS", "BARCLAYS",
    "GOLDMAN", "CREDIT SUISSE", "BNP", "SOCIETE", "(YABANCI)", "YABANCI",
    "TAKASBANK", "MKK", "EUROCLEAR", "CLEARSTREAM",
    "TURK EKONOMI", "TÜRK EKONOMI", "TÜRK EKONOMİ", "TEB",
]
FON_KUME = ["FON", "PORTFÖY", "PORTFOY", "EMEKLİLİK", "EMEKLILIK", "YATIRIM FONU"]
HARIC_SATIRLAR = ["TOPLAM FARK", "TOPLAM", "DİĞER", "DIGER", "DIĞER", "DİGER"]


def kurum_tipi(ad):
    u = ad.upper()
    for kw in YABANCI_SAKLAMA:
        if kw in u:
            return "yabanci"
    for kw in FON_KUME:
        if kw in u:
            return "fon"
    return "yerli"


def haric_mi(ad):
    u = ad.strip().upper()
    return any(u == h or u.startswith(h) for h in HARIC_SATIRLAR)


def norm_ad(ad):
    """İki dosya arası eşleştirme anahtarı: BOM temizle, upper, boşlukları sadeleştir."""
    return " ".join(ad.replace("﻿", "").upper().split())


# ------------------------------------------------------------------ #
# Türkçe sayı parse:  "5.609.214,56" -> 5609214.56 ; "-27.011" -> -27011
# ------------------------------------------------------------------ #
def tr_sayi(s):
    if s is None:
        return None
    s = s.strip().replace("﻿", "").replace("−", "-")
    if s == "" or s.upper() == "NAN":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fmt(n, ondalik=0):
    if n is None:
        return "-"
    neg = n < 0
    n = abs(n)
    if ondalik:
        tam = int(n)
        kus = round((n - tam) * (10 ** ondalik))
        govde = f"{tam:,}".replace(",", ".")
        return ("-" if neg else "") + f"{govde},{str(kus).zfill(ondalik)}"
    govde = f"{int(round(n)):,}".replace(",", ".")
    return ("-" if neg else "") + govde


def _satirlari_oku(yol):
    try:
        with io.open(yol, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))
    except FileNotFoundError:
        sys.exit(f"HATA: dosya bulunamadı: {yol}")
    except Exception as e:
        sys.exit(f"HATA: CSV okunamadı ({yol}): {e}")


# ------------------------------------------------------------------ #
# Takas (T+2) CSV — mevcut format, sabit kolon indeksleri
# 0 Aracı Kurum |1 Takas |2 Pozisyon |3 Tutar |4 Dün Lot |5 Gün Lot |
# 6 Maliyet |7 % |8 Takas Son |9 Tutar Son |10 % Son |11 Adet Fark |...
# ------------------------------------------------------------------ #
def takas_oku(yol):
    satirlar = _satirlari_oku(yol)
    if not satirlar:
        sys.exit("HATA: takas CSV boş.")
    veri = []
    for r in satirlar[1:]:
        if not r or not r[0].strip():
            continue
        ad = r[0].strip().replace("﻿", "")
        if haric_mi(ad):
            continue
        try:
            veri.append({
                "ad": ad, "key": norm_ad(ad), "tip": kurum_tipi(ad),
                "takas": tr_sayi(r[1]), "gun_lot": tr_sayi(r[5]),
                "maliyet": tr_sayi(r[6]), "pay_eski": tr_sayi(r[7]),
                "takas_son": tr_sayi(r[8]), "pay_son": tr_sayi(r[10]),
                "adet_fark": tr_sayi(r[11]),
            })
        except IndexError:
            continue
    if not veri:
        sys.exit("HATA: takas CSV'de işlenebilir kurum satırı yok (kolon düzeni farklı olabilir).")
    return veri


# ------------------------------------------------------------------ #
# Gün içi "Aracı Kurum Dağılımı" CSV — başlık-bazlı esnek kolon tespiti
# (formatı bilmiyoruz: 'Net' varsa onu, yoksa Alış Lot − Satış Lot)
# ------------------------------------------------------------------ #
def gunici_oku(yol):
    satirlar = _satirlari_oku(yol)
    if not satirlar:
        sys.exit("HATA: gün içi CSV boş.")
    head = [h.replace("﻿", "").strip().upper() for h in satirlar[0]]

    def bul(*tokenlar, zorunlu_lot=False):
        for i, h in enumerate(head):
            if all(t in h for t in tokenlar):
                if zorunlu_lot and "LOT" not in h and "ADET" not in h:
                    continue
                return i
        return None

    i_kurum = bul("ARACI") or bul("KURUM") or bul("AÇIKLAMA") or bul("ACIKLAMA") or 0
    i_net = bul("NET")  # 'Net', 'Net Lot', 'Net Adet'...
    i_alis = bul("ALI", "LOT") or bul("ALI", "ADET") or bul("ALIŞ")
    i_satis = bul("SAT", "LOT") or bul("SAT", "ADET") or bul("SATIŞ")

    if i_net is None and (i_alis is None or i_satis is None):
        sys.exit("HATA: gün içi CSV'de 'Net' ya da 'Alış/Satış Lot' kolonu bulunamadı.\n"
                 f"       Bulunan başlıklar: {satirlar[0]}")

    net_map, ad_map = {}, {}
    for r in satirlar[1:]:
        if not r or i_kurum >= len(r) or not r[i_kurum].strip():
            continue
        ad = r[i_kurum].strip().replace("﻿", "")
        if haric_mi(ad):
            continue
        if i_net is not None and i_net < len(r):
            net = tr_sayi(r[i_net])
        else:
            a = tr_sayi(r[i_alis]) if i_alis is not None and i_alis < len(r) else None
            s = tr_sayi(r[i_satis]) if i_satis is not None and i_satis < len(r) else None
            net = (a or 0) - (s or 0) if (a is not None or s is not None) else None
        if net is None:
            net = 0.0
        net_map[norm_ad(ad)] = net
        ad_map[norm_ad(ad)] = ad
    if not net_map:
        sys.exit("HATA: gün içi CSV'de işlenebilir kurum satırı yok.")
    yontem = "Net kolonu" if i_net is not None else "Alış Lot − Satış Lot"
    return net_map, ad_map, yontem


# ------------------------------------------------------------------ #
def baslik(metin):
    print("\n" + "=" * 70)
    print(metin)
    print("=" * 70)


def virman_skoru(k, toplam_takas):
    af = abs(k["adet_fark"] or 0)
    if af == 0 or toplam_takas <= 0:
        return 0.0
    buyukluk = min(af / toplam_takas, 1.0)
    gl = abs(k["gun_lot"] or 0)
    uyumsuzluk = max(0.0, 1.0 - (gl / af))
    skor = 100.0 * (0.55 * buyukluk + 0.45 * uyumsuzluk)
    if k["tip"] in ("yabanci", "fon"):
        skor *= 0.3
    return round(min(skor, 100.0), 1)


# ------------------------------------------------------------------ #
# KESİN VİRMAN bölümü (iki-CSV modu)
# ------------------------------------------------------------------ #
def kesin_virman_bolumu(veri, net_map, ad_map, yontem, toplam_takas, top):
    # Virman anlamlılık eşiği = toplam takasın %0.5'i (gürültü değil; bu kadar
    # takas değişimi "anlamlı" sayılır). Gün içi net küçüklük oranı = %30.
    esik = 0.005 * toplam_takas
    NET_ORAN = 0.30
    baslik("[2] KESİN VİRMAN TESPİTİ (iki-CSV: gün içi NET ↔ T+2 takas ADET FARK)")
    print(f"Gün içi NET kaynağı: {yontem}.")
    print("T+2 mantığı: gün içi işlem 2 iş günü sonra takasa yansır. Takas dosyanı,")
    print("gün içi dosyandan ~2 iş günü SONRAKİ takas olacak şekilde sen seçmelisin.")
    print(f"Virman eşiği: |Adet Fark| ≥ {fmt(esik)} lot (toplam takasın %0.5'i) "
          f"VE |gün içi net| < |Adet Fark| × {NET_ORAN:g}.")

    # Dosya uyumu kontrolü
    takas_keys = {k["key"] for k in veri}
    ortak = takas_keys & set(net_map.keys())
    kucuk = min(len(takas_keys), len(net_map))
    print(f"\nEşleşen kurum: {len(ortak)} / takas {len(takas_keys)}, gün içi {len(net_map)}.")
    if len(ortak) == 0:
        print("‼️  UYARI: Hiç kurum eşleşmedi → bu iki dosya UYUMSUZ olabilir "
              "(farklı hisse/tarih ya da farklı format). Kesin virman atlanıyor.")
        return []
    if len(ortak) < max(3, 0.2 * kucuk):
        print("⚠️  UYARI: Çok az kurum eşleşti → dosyalar aynı hisse/tarihe ait olmayabilir. "
              "Sonuçları temkinli değerlendir.")

    virman, aktif = [], []
    for k in veri:
        if k["key"] not in net_map:
            continue
        af = k["adet_fark"] or 0
        net = net_map[k["key"]] or 0
        if abs(af) < esik:
            continue  # takas anlamlı değişmemiş → ilgilenmiyoruz
        # Takas anlamlı değişti. Gün içi net işlem bunu açıklıyor mu?
        if abs(net) < NET_ORAN * abs(af):
            virman.append((k, af, net))   # gün içi işlem ≈ 0 → takas TRANSFERLE değişti = VİRMAN
        else:
            aktif.append((k, af, net))     # gün içi net büyük → işlem/aracılık açıklıyor, VİRMAN DEĞİL

    virman.sort(key=lambda t: -abs(t[1]))
    aktif.sort(key=lambda t: -abs(t[2]))

    print("\n  🔴 GERÇEK VİRMAN (takas anlamlı değişti AMA gün içi net işlem küçük → transfer, satış/alış DEĞİL):")
    if virman:
        for k, af, net in virman[:top]:
            print(f"    {k['ad']:<22} takas Adet Fark {fmt(af):>13} | gün içi net {fmt(net):>13}"
                  f" | takas son {fmt(k['takas_son'])} | tip:{k['tip']}")
    else:
        print("    (yok)")

    print("\n  ⚪ ELENEN — AKTİF ARACILIK (takas değişti ama gün içi net işlem büyük → VİRMAN DEĞİL):")
    if aktif:
        for k, af, net in aktif[:top]:
            print(f"    {k['ad']:<22} takas Adet Fark {fmt(af):>13} | gün içi net {fmt(net):>13}"
                  f" | tip:{k['tip']}  → işlem açıklıyor, elendi")
    else:
        print("    (yok)")

    return virman


# ------------------------------------------------------------------ #
def analiz(veri, hisse, esik, top, gunici=None):
    toplam_takas = sum(k["takas_son"] or 0 for k in veri)
    gurultu = esik * toplam_takas
    iki_csv = gunici is not None

    print("#" * 70)
    print(f"#  TAKAS İŞARET ANALİZİ — {hisse or '(hisse etiketi verilmedi)'}"
          f"   [{'İKİ-CSV / KESİN' if iki_csv else 'TEK-CSV / ŞÜPHE'} modu]")
    print("#" * 70)
    print(f"Kurum sayısı (analize dahil): {len(veri)}")
    print(f"Toplam güncel takas (Takas Son): {fmt(toplam_takas)} lot")
    print(f"Gürültü eşiği: %{esik*100:g}  (|Adet Fark| < {fmt(gurultu)} lot olanlar yok sayılır)")
    if hisse is None:
        print("NOT: CSV'de sembol kolonu yok; --hisse yalnızca etikettir, filtre değildir.")
    print("UYARI: Bu araç yalnız İŞARET üretir, AL/SAT TAVSİYESİ VERMEZ. Karar insana aittir.")

    anlamli = [k for k in veri if abs(k["adet_fark"] or 0) >= gurultu]

    # --- 1) OLASI PATRON ÇIKIŞI ------------------------------------------ #
    cikislar = [k for k in anlamli
                if (k["adet_fark"] or 0) < 0 and toplam_takas > 0
                and abs(k["adet_fark"]) / toplam_takas > 0.05]
    cikislar.sort(key=lambda k: k["adet_fark"])
    baslik("⚠️  [1] OLASI PATRON ÇIKIŞI / BOŞALTMA ŞÜPHESİ")
    if cikislar:
        print("Tek bir kurumda toplam takasın %5'inden fazla ÇIKIŞ var:")
        for k in cikislar:
            pay = abs(k["adet_fark"]) / toplam_takas * 100
            print(f"  ‼️  {k['ad']:<22} çıkış {fmt(k['adet_fark'])} lot "
                  f"(tahtanın ~%{pay:.1f}'i) | maliyet {fmt(k['maliyet'],2)} "
                  f"| pay %{(k['pay_eski'] or 0):.2f} → %{(k['pay_son'] or 0):.2f} | tip:{k['tip']}")
        print("  → Patron/oyuncu boşaltma şüphesi. KAP + gün-içi işlemle DOĞRULA.")
    else:
        print("  Yok. %5'i aşan tek-kurum çıkışı tespit edilmedi.")

    # --- 2) KESİN VİRMAN (iki-CSV) ya da ŞÜPHE (tek-CSV) ------------------ #
    if iki_csv:
        net_map, ad_map, yontem = gunici
        virman = kesin_virman_bolumu(veri, net_map, ad_map, yontem, toplam_takas, top)
        virman_bulgu = [f"{k['ad']} (takas {fmt(af)}, gün içi net {fmt(net)})"
                        for k, af, net in virman]
        virman_kurumlar = [k["ad"] for k, af, net in virman]
    else:
        suspheli = []
        for k in anlamli:
            af = abs(k["adet_fark"] or 0)
            gl = abs(k["gun_lot"] or 0)
            if af > 0 and gl < 0.20 * af:
                k2 = dict(k); k2["skor"] = virman_skoru(k, toplam_takas)
                suspheli.append(k2)
        suspheli.sort(key=lambda k: k["skor"], reverse=True)
        asil = [k for k in suspheli if k["tip"] == "yerli" and k["skor"] >= 1]
        ikincil = [k for k in suspheli if k not in asil]
        virman_bulgu = [f"{k['ad']} (skor {k['skor']:.1f}, Adet Fark {fmt(k['adet_fark'])})"
                        for k in asil[:top]]
        virman_kurumlar = [k["ad"] for k in asil[:top]]
        baslik("[2] VİRMAN ŞÜPHESİ (TEK-CSV sezgisel: Adet Fark büyük ama Gün Lot küçük) + SKOR")
        print("NOT: Kesinleştirmek için --gunici <gün içi dağılım CSV> ekle.")
        print("\n  ASIL ŞÜPHELİLER (yerli kurum, yüksek skor):")
        for k in (asil[:top] or [None]):
            if k is None: print("    (yok)"); break
            print(f"    skor {k['skor']:5.1f} | {k['ad']:<22} Adet Fark {fmt(k['adet_fark'])} "
                  f"| Gün Lot {fmt(k['gun_lot'])} | takas son {fmt(k['takas_son'])}")
        print("\n  İKİNCİL (yabancı/saklama/fon — genelde mekanik, skor düşürüldü):")
        for k in (ikincil[:top] or [None]):
            if k is None: print("    (yok)"); break
            print(f"    skor {k['skor']:5.1f} | {k['ad']:<22} Adet Fark {fmt(k['adet_fark'])} "
                  f"| Gün Lot {fmt(k['gun_lot'])} | tip:{k['tip']}")

    # --- 3) EKSİ TAKAS --------------------------------------------------- #
    eksi = [k for k in anlamli
            if (k["adet_fark"] or 0) < 0 and (k["takas_son"] or 0) < abs(k["adet_fark"] or 0)]
    eksi.sort(key=lambda k: k["adet_fark"])
    baslik("[3] EKSİ TAKAS — elinde olmayan / virman malı satışı")
    print("Mantık: Takas Son < |Adet Fark| → kurum, takasında o kadar lotu yokken büyük çıkış yaptı.")
    if eksi:
        for k in eksi[:top]:
            print(f"  • {k['ad']:<22} çıkış {fmt(k['adet_fark'])} lot "
                  f"| takas son sadece {fmt(k['takas_son'])} lot | tip:{k['tip']}")
        print("  → Virman malı satışı / arka kapı çıkışı işareti.")
    else:
        print("  Yok.")

    # --- 4) OYUNCU + MALİYET / HAYAT ÇİZGİSİ ----------------------------- #
    oyuncular = [k for k in veri if (k["maliyet"] or 0) > 0 and k["tip"] != "fon"]
    oyuncular.sort(key=lambda k: (k["takas_son"] or 0), reverse=True)
    maliyet_bandi = None
    baslik("[4] OYUNCU + MALİYET (maliyeti olanlar = saklama/fon değil) / HAYAT ÇİZGİSİ")
    if oyuncular:
        for k in oyuncular[:top]:
            yon = "ALIŞ" if (k["adet_fark"] or 0) > 0 else ("SATIŞ" if (k["adet_fark"] or 0) < 0 else "—")
            print(f"  {k['ad']:<22} takas {fmt(k['takas_son']):>12} lot "
                  f"| maliyet {fmt(k['maliyet'],2):>8} | pay %{(k['pay_son'] or 0):.2f} | {yon}")
        net_alici = [k for k in oyuncular if (k["adet_fark"] or 0) > 0]
        lot_top = sum(k["adet_fark"] for k in net_alici)
        if lot_top > 0:
            agirlikli = sum(k["adet_fark"] * k["maliyet"] for k in net_alici) / lot_top
            mals = sorted(k["maliyet"] for k in net_alici)
            maliyet_bandi = (f"~{fmt(agirlikli,2)} (medyan {fmt(mals[len(mals)//2],2)}, "
                             f"aralık {fmt(mals[0],2)}–{fmt(mals[-1],2)})")
            print(f"\n  → Net ALICI oyuncuların lot-ağırlıklı ort. maliyeti (HAYAT ÇİZGİSİ bandı): "
                  f"~{fmt(agirlikli,2)}  (medyan {fmt(mals[len(mals)//2],2)}, "
                  f"aralık {fmt(mals[0],2)}–{fmt(mals[-1],2)})")
        else:
            print("\n  → Bu kesitte net alıcı oyuncu yok; hayat çizgisi bandı hesaplanamadı.")
    else:
        print("  Maliyeti tanımlı oyuncu kurum bulunamadı.")

    # --- 5) NET ALICI / SATICI ------------------------------------------- #
    baslik("[5] NET ALICI / SATICI (Adet Fark) — bağlam")
    alicilar = sorted([k for k in anlamli if (k["adet_fark"] or 0) > 0],
                      key=lambda k: k["adet_fark"], reverse=True)
    saticilar = sorted([k for k in anlamli if (k["adet_fark"] or 0) < 0], key=lambda k: k["adet_fark"])
    print("  En çok NET ALAN:")
    for k in (alicilar[:top] or [None]):
        if k is None: print("    (yok)"); break
        print(f"    +{fmt(k['adet_fark']):>12} lot | {k['ad']:<22} (%{(k['pay_son'] or 0):.2f}, {k['tip']})")
    print("  En çok NET SATAN:")
    for k in (saticilar[:top] or [None]):
        if k is None: print("    (yok)"); break
        print(f"    {fmt(k['adet_fark']):>13} lot | {k['ad']:<22} (%{(k['pay_son'] or 0):.2f}, {k['tip']})")

    # --- 6) ATLANANLAR --------------------------------------------------- #
    baslik("[6] BU VERİYLE HESAPLANAMAYAN KURALLAR (atlandı)")
    atlanan = [
        "Çok-günlük zaman serisi (yatay band/süpürme/dans aşaması) — birden çok günün CSV'si gerekir.",
        "KAP teyidi (işlem gören tipe dönüşüm, pay satış formu, SPK yasağı) — KAP kaynağı gerekir.",
        "%5 nitelikli yatırımcı isimlendirme + 'düşme vs çıkma' — KAP/MKK bildirimi gerekir.",
        "TEFAS açık/kapalı fon künyesi (özel fon tespiti) — TEFAS/Fintables gerekir.",
        "OHLCV / formasyon / fiyat hedefi — fiyat verisi + insan yorumu gerekir.",
    ]
    if not iki_csv:
        atlanan.insert(0, "KESİN virman eşleştirme — gün içi dağılım CSV'si (--gunici) eklenmedi.")
    for s in atlanan:
        print(f"  – {s}")
    print("\n(Bu kurallar uydurulmadı; veri olmadığı için hesaplanmadı.)")

    # --- ÇAPRAZ DOĞRULAMA (Modül 4 / Faz 3) ----------------------------- #
    sinyaller = {}
    for k in cikislar:
        _sinyal_ekle(sinyaller, k["ad"], "patron çıkışı")
    for ad in virman_kurumlar:
        _sinyal_ekle(sinyaller, ad, "virman")
    for k in eksi:
        _sinyal_ekle(sinyaller, k["ad"], "eksi takas")
    guven = capraz_dogrulama(hisse, sinyaller, [], top=top)

    print("\n" + "#" * 70)
    print("#  Son söz: Araç işaret verir, KARAR İNSANA AİTTİR.  (AL/SAT tavsiyesi yoktur.)")
    print("#" * 70)

    # --- Deftere yazılacak bulguları topla (Modül 3 / Faz 1) ------------- #
    patron_bulgu = [
        f"{k['ad']} çıkış {fmt(k['adet_fark'])} lot (~%{abs(k['adet_fark'])/toplam_takas*100:.1f})"
        for k in cikislar] if toplam_takas > 0 else []
    eksi_bulgu = [f"{k['ad']} çıkış {fmt(k['adet_fark'])} lot (takas son {fmt(k['takas_son'])})"
                  for k in eksi[:top]]
    oyuncu_bulgu = [f"{k['ad']} (takas {fmt(k['takas_son'])}, maliyet {fmt(k['maliyet'],2)})"
                    for k in oyuncular[:5]]
    net_alici_bulgu = [f"{k['ad']} +{fmt(k['adet_fark'])}" for k in alicilar[:3]]
    net_satici_bulgu = [f"{k['ad']} {fmt(k['adet_fark'])}" for k in saticilar[:3]]
    return {
        "hisse": hisse,
        "mod": "iki-CSV (kesin virman)" if iki_csv else "tek-CSV (şüphe)",
        "patron": patron_bulgu,
        "virman": virman_bulgu,
        "eksi": eksi_bulgu,
        "oyuncular": oyuncu_bulgu,
        "maliyet_bandi": maliyet_bandi,
        "net_alici": net_alici_bulgu,
        "net_satici": net_satici_bulgu,
        "guven": guven,
    }


# ------------------------------------------------------------------ #
# DEFTER / KAYIT (Modül 3 — Faz 1)
# her analizi kayitlar/HISSE.md defterine EKLER (üstüne yazmaz)
# ------------------------------------------------------------------ #
AYRAC = "─" * 60


def _liste(b, bos="(yok)"):
    """Bulgu listesini madde madde markdown'a çevir; boşsa '(yok)'."""
    if not b:
        return f"  - {bos}"
    return "\n".join(f"  - {x}" for x in b)


def _onceki_kayit(metin):
    """Defterdeki son KAYIT meta'sından (tarih, ana bulgu) çek; yoksa None."""
    son = None
    for satir in metin.splitlines():
        s = satir.strip()
        if s.startswith("<!-- KAYIT "):
            tarih = ana = ""
            for parca in ('tarih="', 'ana="'):
                if parca in s:
                    deger = s.split(parca, 1)[1].split('"', 1)[0]
                    if parca.startswith("tarih"):
                        tarih = deger
                    else:
                        ana = deger
            son = (tarih, ana)
    return son


def _defter_ekle(hisse, ana, govde, baslik_eki=""):
    """Düşük seviye defter yazıcı: yol/klasör/başlık/meta/kıyas/ayraç + EKLEME.
    govde: markdown gövde satırları listesi. ana: meta+kıyas için kısa özet."""
    hisse = (hisse or "GENEL").strip().upper()
    klasor = "kayitlar"
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, f"{hisse}.md")
    var = os.path.exists(yol)

    damga = datetime.now().strftime("%Y-%m-%d %H:%M")
    onceki = None
    if var:
        with io.open(yol, "r", encoding="utf-8") as f:
            onceki = _onceki_kayit(f.read())

    parcalar = []
    if not var:
        parcalar.append(f"# {hisse} — TAKAS ANALİZ DEFTERİ\n\n"
                        "> Araç işaret verir, KARAR İNSANA AİTTİR. AL/SAT tavsiyesi yoktur.\n")
    parcalar.append(f'<!-- KAYIT tarih="{damga}" ana="{ana}" -->')
    parcalar.append(f"## {damga} — {hisse}{baslik_eki}\n")
    if onceki:
        parcalar.append(f"> **Kıyas:** Önceki analiz: {onceki[0]}, {onceki[1]}. "
                        "Şimdi tekrar bakılıyor.\n")
    parcalar.extend(govde)
    parcalar.append(f"\n{AYRAC}\n")

    blok = ("\n" if var else "") + "\n".join(parcalar) + "\n"
    with io.open(yol, "a", encoding="utf-8") as f:
        f.write(blok)
    return yol


def defter_yaz(bulgu, aralik):
    if bulgu["patron"]:
        ana = "patron çıkışı: " + bulgu["patron"][0]
    elif bulgu["virman"]:
        ana = "virman: " + bulgu["virman"][0]
    else:
        ana = "belirgin patron/virman yok"
    govde = [
        f"- **Veri aralığı:** {aralik or 'belirtilmedi'}",
        f"- **Mod:** {bulgu['mod']}",
        f"- **Patron çıkışı:**\n{_liste(bulgu['patron'])}",
        f"- **Virman:**\n{_liste(bulgu['virman'])}",
        f"- **Eksi takas:**\n{_liste(bulgu['eksi'])}",
        f"- **Oyuncular (ilk 5):**\n{_liste(bulgu['oyuncular'])}",
        f"- **Hayat çizgisi (maliyet bandı):** {bulgu['maliyet_bandi'] or '(hesaplanamadı)'}",
        f"- **Net alıcı (ilk 3):**\n{_liste(bulgu['net_alici'])}",
        f"- **Net satıcı (ilk 3):**\n{_liste(bulgu['net_satici'])}",
        f"- **📌 Güven özeti:** {bulgu.get('guven') or '(yok)'}",
    ]
    return _defter_ekle(bulgu["hisse"], ana, govde)


# ------------------------------------------------------------------ #
# ÇAPRAZ DOĞRULAMA / GÜVEN (Modül 4 — Faz 3)
# tek sinyale güvenme: bir kurum kaç bağımsız işarette görünüyor?
# ------------------------------------------------------------------ #
def _sinyal_ekle(sinyaller, ad, etiket):
    sinyaller.setdefault(ad, [])
    if etiket not in sinyaller[ad]:
        sinyaller[ad].append(etiket)


def capraz_dogrulama(hisse, sinyaller, degisimler, top=15):
    """sinyaller: {kurum: [kanıt etiketi,...]}. degisimler: [(kurum, açıklama)].
    Sinyalleri birleştirir, defter geçmişiyle kıyaslar, güven özeti döndürür."""
    baslik("[★] ÇAPRAZ DOĞRULAMA / GÜVEN — tek sinyale güvenme, kanıtları birleştir")
    print("Mantık: bir kurum ne kadar çok BAĞIMSIZ işarette görünürse sinyal o kadar güçlü.")
    if not sinyaller:
        print("  Belirgin sinyal yok; çapraz doğrulama yapılmadı.")
        return "Belirgin örtüşen sinyal yok."

    sirali = sorted(sinyaller.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    guclu = [(a, s) for a, s in sirali if len(s) >= 3]
    orta = [(a, s) for a, s in sirali if len(s) == 2]
    zayif = [(a, s) for a, s in sirali if len(s) == 1]

    print("\n  🔴 GÜÇLÜ (3+ kanıt — sinyaller örtüşüyor):")
    print("\n".join(f"    {a:<22} {len(s)} kanıt: {', '.join(s)}" for a, s in guclu) or "    (yok)")
    print("\n  🟡 ORTA (2 kanıt):")
    print("\n".join(f"    {a:<22} {len(s)} kanıt: {', '.join(s)}" for a, s in orta) or "    (yok)")
    print("\n  ⚪ ZAYIF (1 kanıt — tek işaret, temkinli ol):")
    print("\n".join(f"    {a:<22} {s[0]}" for a, s in zayif[:top]) or "    (yok)")

    # Defterle tutarlılık (önceki bloklarda da var mı?)
    yol = os.path.join("kayitlar", f"{(hisse or 'GENEL').strip().upper()}.md")
    prior = ""
    if os.path.exists(yol):
        with io.open(yol, "r", encoding="utf-8") as f:
            prior = f.read().upper()
    izlenen = [a for a, _ in guclu] + [a for a, _ in orta]
    print("\n  📚 DEFTERLE TUTARLILIK (geçmiş kayıtlar):")
    if not prior:
        print("    (defter yeni — geçmiş kıyas yok; bu ilk kayıt)")
    elif not izlenen:
        print("    (güçlü/orta sinyal yok; kıyas atlandı)")
    else:
        for a in izlenen:
            if a.upper() in prior:
                print(f"    {a:<22} geçmişte de görüldü → SÜREKLİLİK var (gerçek oyuncu işareti)")
            else:
                print(f"    {a:<22} ilk kez → YENİ (tek seferlik olabilir)")

    # Yön değişimi (çelişki değil, davranış değişimi)
    print("\n  🔁 YÖN DEĞİŞİMİ (çelişki değil, davranış değişimi — incele):")
    print("\n".join(f"    {a:<22} {ack}" for a, ack in degisimler[:top]) or "    (yok)")

    # Güven özeti
    parcalar = []
    if guclu:
        a, s = guclu[0]
        parcalar.append(f"En güçlü sinyal: {a} ({len(s)} kanıt: {', '.join(s)})")
    elif orta:
        a, s = orta[0]
        parcalar.append(f"En güçlü sinyal: {a} (2 kanıt: {', '.join(s)})")
    elif zayif:
        parcalar.append(f"En güçlü sinyal: {zayif[0][0]} (tek kanıt — zayıf)")
    if degisimler:
        a, ack = degisimler[0]
        parcalar.append(f"En dikkat çeken değişim: {a} ({ack})")
    ozet = (". ".join(parcalar) + ".") if parcalar else "Belirgin örtüşen sinyal yok."
    print("\n  📌 GÜVEN ÖZETİ: " + ozet)
    print("  (Not: 'güçlü sinyal' = kanıtlar örtüşüyor demektir; AL/SAT tavsiyesi DEĞİL.)")
    return ozet


# ------------------------------------------------------------------ #
# ÇOKLU ARALIK KARŞILAŞTIRMA (Modül 2 — Faz 2)
# geniş→dar aralıkları karşılaştır: daraltınca kaybolmayan = kalıcı virman
# ------------------------------------------------------------------ #
KALICI_ORAN = 0.30   # en dar |Adet Fark| >= en geniş × bu oran → KALICI


def _af_imzali(v):
    """Adet Fark'ı işaretli string: pozitife '+' ekle."""
    return ("+" if (v or 0) > 0 else "") + fmt(v or 0)


def karsilastir_oku(arg):
    """'dosya:etiket' → (dosya, etiket). Etiket yoksa dosya adını kullan."""
    if ":" in arg:
        dosya, etiket = arg.rsplit(":", 1)
        etiket = etiket.strip() or dosya
    else:
        dosya, etiket = arg, arg
    return dosya, etiket


def karsilastir(dosya_etiketler, hisse, aralik=None, top=15):
    if len(dosya_etiketler) < 2:
        sys.exit("HATA: --karsilastir en az 2 dosya ister (biçim: dosya:etiket).")

    araliklar = []  # geniş→dar sırada
    for arg in dosya_etiketler:
        dosya, etiket = karsilastir_oku(arg)
        veri = takas_oku(dosya)
        toplam = sum(k["takas_son"] or 0 for k in veri)
        araliklar.append({
            "etiket": etiket,
            "toplam": toplam,
            "af": {k["key"]: (k["adet_fark"] or 0) for k in veri},
            "takas_son": {k["key"]: (k["takas_son"] or 0) for k in veri},
            "ad": {k["key"]: k["ad"] for k in veri},
            "tip": {k["key"]: k["tip"] for k in veri},
        })

    # Belirginlik eşiği EN DAR aralığa göre (sonuncu dosya). Geniş aralığın
    # devasa toplamı gerçek oyuncuları (birkaç yüz bin lot) elemesin diye.
    dar_iv = araliklar[-1]
    floor = 0.005 * dar_iv["toplam"]

    etiketler = [iv["etiket"] for iv in araliklar]
    print("#" * 70)
    print(f"#  ÇOKLU ARALIK KARŞILAŞTIRMA — {hisse or '(hisse verilmedi)'}")
    print(f"#  Aralıklar (geniş→dar): {' → '.join(etiketler)}")
    print("#" * 70)
    print("Mantık: bir kurum daraltınca KAYBOLMUYORSA = kalıcı virman tarafı.")
    print(f"Ölçü: en dar |Adet Fark| ≥ en geniş × %{KALICI_ORAN*100:g} → KALICI.")
    print(f"Belirginlik eşiği: |Adet Fark| ≥ {fmt(floor)} lot (en dar aralık "
          f"'{etiketler[-1]}' toplam takasının %0.5'i).")
    print("Yabancı/saklama kurumlar (mekanik aracılık) ana sınıflandırmadan ÇIKARILIR.")
    print("UYARI: Bu araç yalnız İŞARET üretir, AL/SAT TAVSİYESİ VERMEZ. Karar insana aittir.")
    print(f"T+2 notu: geniş aralık karşılaştırıldığı için kayma önemsiz; AMA en dar aralık "
          f"('{etiketler[-1]}') birkaç günse T+2 kaymasına dikkat et.")

    # Birleşik kurum listesi — her aralıktaki Adet Fark
    keys = set()
    for iv in araliklar:
        keys |= set(iv["af"].keys())

    satirlar = []   # yerli/fon: (ad, tip, afs[], genis_af, dar_af, oran, kategori)
    mekanik = []    # yabancı/saklama: (ad, tip, afs[])
    for key in keys:
        afs = [iv["af"].get(key, 0) for iv in araliklar]
        if max(abs(v) for v in afs) < floor:
            continue  # hiçbir aralıkta belirgin değil
        ad = next((iv["ad"][key] for iv in araliklar if key in iv["ad"]), key)
        tip = next((iv["tip"][key] for iv in araliklar if key in iv["tip"]), "yerli")
        if tip == "yabanci":
            mekanik.append((ad, tip, afs))   # virman değil, mekanik aracılık → ayrı liste
            continue
        genis_af, dar_af = afs[0], afs[-1]
        oran = (abs(dar_af) / abs(genis_af)) if genis_af else float("inf")
        ayni_yon = (genis_af > 0) == (dar_af > 0)
        if genis_af == 0 or oran >= 1.0 or (oran >= KALICI_ORAN and not ayni_yon):
            kategori = "yogun"      # dar dönemde oransal büyümüş / yön değişmiş → odak o tarihte
        elif oran >= KALICI_ORAN:
            kategori = "kalici"     # daraltınca kaybolmuyor → gerçek virman tarafı
        else:
            kategori = "gurultu"    # daraldıkça kayboluyor → dağınık işlem
        satirlar.append((ad, tip, afs, genis_af, dar_af, oran, kategori))

    # --- Tablo (yalnız yerli/fon) ---
    baslik("[1] ARALIK TABLOSU — yerli/fon kurum × aralık (Adet Fark)")
    if not satirlar:
        print("  Hiçbir yerli/fon kurum belirgin değil (en dar eşik altı).")
    else:
        basl = f"  {'Kurum':<22}" + "".join(f"{e:>15}" for e in etiketler)
        print(basl)
        print("  " + "-" * (len(basl) - 2))
        for ad, tip, afs, *_ in sorted(satirlar, key=lambda s: -abs(s[3]))[:max(top, 25)]:
            print(f"  {ad:<22}" + "".join(f"{_af_imzali(v):>15}" for v in afs))

    def _ozet(s):
        ad, tip, afs, genis_af, dar_af, oran, _ = s
        oran_str = "∞" if oran == float("inf") else f"%{oran*100:.0f}"
        return (f"{ad:<22} {etiketler[0]} {_af_imzali(genis_af):>12} → "
                f"{etiketler[-1]} {_af_imzali(dar_af):>12} (oran {oran_str}) | tip:{tip}")

    kalici = sorted([s for s in satirlar if s[6] == "kalici"], key=lambda s: -abs(s[4]))
    yogun = sorted([s for s in satirlar if s[6] == "yogun"], key=lambda s: -abs(s[4]))
    gurultu = sorted([s for s in satirlar if s[6] == "gurultu"], key=lambda s: -abs(s[3]))

    baslik("[2] SINIFLANDIRMA (yalnız yerli/fon)")
    print("\n  🔴 KALICI VİRMAN (daraltınca KAYBOLMUYOR → gerçek virman tarafı):")
    print("\n".join(f"    {_ozet(s)}" for s in kalici[:top]) or "    (yok)")
    print("\n  🟠 YOĞUNLAŞMA (dar dönemde oransal BÜYÜYOR/yön değişti → o tarihe odaklan):")
    print("\n".join(f"    {_ozet(s)}" for s in yogun[:top]) or "    (yok)")
    print("\n  ⚪ GÜRÜLTÜ / DAĞINIK (daraldıkça küçülüyor/kayboluyor → gerçek operasyon değil):")
    print("\n".join(f"    {_ozet(s)}" for s in gurultu[:top]) or "    (yok)")

    # --- Yabancı/saklama (mekanik, elendi) ---
    baslik("[3] YABANCI / SAKLAMA (mekanik aracılık — sınıflandırmaya ALINMADI)")
    mekanik.sort(key=lambda m: -abs(m[2][0]))
    if mekanik:
        for ad, tip, afs in mekanik[:top]:
            print(f"  {ad:<22}" + "".join(f"{_af_imzali(v):>15}" for v in afs))
        print("  → Saklama/aracılık. Büyük rakamlar virman değil; bu yüzden elendi.")
    else:
        print("  (belirgin yabancı/saklama kurum yok)")

    # --- En dar aralıkta en hareketli yerli kurumlar ("şu an ne oluyor") ---
    baslik(f"[4] EN DAR ARALIKTA ('{etiketler[-1]}') EN HAREKETLİ YERLİ KURUMLAR — şu an ne oluyor")
    hareketli = []
    for key in dar_iv["af"]:
        if dar_iv["tip"].get(key) == "yabanci":
            continue
        hareketli.append((dar_iv["ad"][key], dar_iv["af"][key],
                          dar_iv["takas_son"].get(key, 0), dar_iv["tip"][key]))
    hareketli.sort(key=lambda t: -abs(t[1]))
    if hareketli:
        for ad, af, ts, tip in hareketli[:10]:
            yon = "ALIŞ" if af > 0 else ("SATIŞ" if af < 0 else "—")
            print(f"  {ad:<22} Adet Fark {_af_imzali(af):>13} | takas son {fmt(ts):>13} | {yon} | tip:{tip}")
    else:
        print("  (yerli kurum yok)")

    # --- ÇAPRAZ DOĞRULAMA (Modül 4 / Faz 3) ----------------------------- #
    sinyaller = {}
    for s in kalici:
        _sinyal_ekle(sinyaller, s[0], "kalıcı virman")
    for s in yogun:
        _sinyal_ekle(sinyaller, s[0], "yoğunlaşma")
    degisim_ham = []
    for ad, tip, afs, genis_af, dar_af, oran, kat in satirlar:
        if genis_af and dar_af and (genis_af > 0) != (dar_af > 0):
            ack = (f"{etiketler[0]} {'alıcı' if genis_af > 0 else 'satıcı'} → "
                   f"{etiketler[-1]} {'alıcı' if dar_af > 0 else 'satıcı'}")
            degisim_ham.append((abs(dar_af), ad, ack))
            _sinyal_ekle(sinyaller, ad, "yön değişimi")
    for ad, af, ts, tip in hareketli[:10]:
        _sinyal_ekle(sinyaller, ad, "son ayda çok hareketli")
    degisim_ham.sort(key=lambda t: -t[0])
    degisimler = [(ad, ack) for _, ad, ack in degisim_ham]
    guven = capraz_dogrulama(hisse, sinyaller, degisimler, top=top)

    print("\n" + "#" * 70)
    print("#  Son söz: Araç işaret verir, KARAR İNSANA AİTTİR.  (AL/SAT tavsiyesi yoktur.)")
    print("#" * 70)

    # --- Deftere yaz ---
    kalici_l = [f"{s[0]} ({etiketler[0]} {_af_imzali(s[3])} → {etiketler[-1]} {_af_imzali(s[4])}, "
                f"oran {'∞' if s[5]==float('inf') else f'%{s[5]*100:.0f}'})" for s in kalici[:top]]
    yogun_l = [f"{s[0]} ({etiketler[0]} {_af_imzali(s[3])} → {etiketler[-1]} {_af_imzali(s[4])})"
               for s in yogun[:top]]
    gurultu_l = [f"{s[0]} ({etiketler[0]} {_af_imzali(s[3])} → {etiketler[-1]} {_af_imzali(s[4])})"
                 for s in gurultu[:top]]
    mekanik_l = [f"{ad} ({' / '.join(_af_imzali(v) for v in afs)})" for ad, tip, afs in mekanik[:top]]
    hareketli_l = [f"{ad} (Adet Fark {_af_imzali(af)}, takas son {fmt(ts)})"
                   for ad, af, ts, tip in hareketli[:10]]
    ana = ("kalıcı virman: " + kalici[0][0]) if kalici else "kalıcı virman yok"
    govde = [
        f"- **Veri aralığı:** {aralik or 'belirtilmedi'}",
        f"- **Mod:** çoklu aralık karşılaştırma ({' → '.join(etiketler)})",
        f"- **🔴 Kalıcı virman (daraltınca kaybolmuyor):**\n{_liste(kalici_l)}",
        f"- **🟠 Yoğunlaşma (dar dönemde arttı):**\n{_liste(yogun_l)}",
        f"- **⚪ Gürültü/dağınık (daralınca kayboldu):**\n{_liste(gurultu_l)}",
        f"- **Yabancı/saklama (mekanik, elendi):**\n{_liste(mekanik_l)}",
        f"- **En dar aralıkta en hareketli yerliler:**\n{_liste(hareketli_l)}",
        f"- **📌 Güven özeti:** {guven}",
    ]
    yol = _defter_ekle(hisse, ana, govde, baslik_eki=" (ÇOKLU ARALIK KARŞILAŞTIRMA)")
    print(f"\n→ {yol} dosyasına kaydedildi.")


def main():
    ap = argparse.ArgumentParser(
        description="Takas işaret aracı (AL/SAT demez). Tek CSV=şüphe, --gunici ile=KESİN virman.")
    ap.add_argument("takas", nargs="?", default=None,
                    help="T+2 takas/aracı kurum dağılımı CSV yolu (tek/iki-CSV modu)")
    ap.add_argument("--gunici", default=None, help="Gün içi aracı kurum dağılımı CSV (KESİN virman için)")
    ap.add_argument("--karsilastir", nargs="+", default=None, metavar="DOSYA:ETIKET",
                    help="Çoklu aralık karşılaştırma: 'dosya:etiket' (geniş→dar sırada, en az 2)")
    ap.add_argument("--hisse", default=None, help="Hisse etiketi (CSV'de sembol yok; sadece başlık)")
    ap.add_argument("--esik", type=float, default=0.01, help="Gürültü eşiği (toplam takas oranı; vars. 0.01)")
    ap.add_argument("--top", type=int, default=15, help="Listelerde gösterilecek satır sayısı")
    ap.add_argument("--aralik", default=None,
                    help="Veri aralığı (serbest metin, örn. '2026 Nisan'); deftere yazılır")
    a = ap.parse_args()

    if a.karsilastir:
        karsilastir(a.karsilastir, a.hisse, aralik=a.aralik, top=a.top)
        return

    if not a.takas:
        ap.error("takas CSV gerekli (ya da --karsilastir kullan).")
    veri = takas_oku(a.takas)
    gunici = gunici_oku(a.gunici) if a.gunici else None
    bulgu = analiz(veri, a.hisse, a.esik, a.top, gunici=gunici)
    yol = defter_yaz(bulgu, a.aralik)
    print(f"\n→ {yol} dosyasına kaydedildi.")


if __name__ == "__main__":
    main()
