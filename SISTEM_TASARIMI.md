# SİSTEM TASARIMI — Takas Analiz Asistanı

## Sistem amacı

Eğitmenin **elle yaptığı takas analizini** sistematik bir asistana çevirmek.
Araç **AL/SAT demez**; **işaret + kayıt + yönlendirme** üretir. **Karar insana aittir.**

---

## Veri

- İki CSV ile çalışır:
  1. **Takas Analizi** (`Aracı Kurum`, `Adet Fark`, `Takas Son`, `Maliyet`, ...)
  2. **Aracı Kurum Dağılımı** (`Açıklama`, `Alım`, `Satım`, `Net`, ...)
- İki dosya **aynı geniş tarih aralığını** kapsamalı.
- Kullanıcı veriyi **geniş aralık** (aylık / yıllık) olarak çeker.

---

## T+2 kuralı

- Gün içi işlem **2 iş günü sonra** takasa yansır.
- **Geniş aralıkta (aylık ve üzeri):** bu 2 günlük kayma önemsizdir → araç iki dosyayı **doğrudan karşılaştırır.**
- **Dar aralıkta (birkaç gün):** kayma sonucu bozabilir → araç kullanıcıyı **uyarır.**

---

## Modüller

| Modül | Durum | İşlev |
|-------|-------|-------|
| **Modül 1** | ✅ ÇALIŞIYOR | Tek aralık analizi — virman, patron çıkışı, eksi takas, oyuncu/maliyet |
| **Modül 2** | ⏳ Yapılacak | Tarih daraltma + zincir takibi — kullanıcı geniş→dar aralıklar verir; araç "hangi kurum daraltınca kaybolmuyor = gerçek virman" der |
| **Modül 3** | 🔨 ŞİMDİ | Kayıt / not alma — her analizi `kayitlar/HISSE.md` defterine yazar |
| **Modül 4** | ⏳ Yapılacak | Çapraz doğrulama |
| **Modül 5** | ⏳ Yapılacak | KAP teyidi (dış kaynak) |
| **Modül 6** | ⏳ Yapılacak | Çoklu tarama (hisse + kurum) |

---

## Klasör yapısı

```
takas_otomasyon/
├── takas_analiz.py        # ana araç (Modül 1)
├── SISTEM_TASARIMI.md     # bu belge
├── veri/                  # çekilen CSV'ler (girdi)
├── kayitlar/              # araç buraya yazar (HISSE.md defterleri)
└── tarama/                # çoklu tarama çıktıları
```

---

## Faz sırası

1. **Faz 1 — Kayıt** (şimdi) → Modül 3
2. **Faz 2 — Tarih daraltma** → Modül 2
3. **Faz 3 — Çapraz doğrulama** → Modül 4
4. **Faz 4 — KAP teyidi** → Modül 5
5. **Faz 5 — Çoklu tarama** → Modül 6

---

> **Son söz:** Araç işaret verir, **KARAR İNSANA AİTTİR.** AL/SAT tavsiyesi yoktur.
