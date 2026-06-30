# DEĞİŞİKLİKLER — Anayasa (ANA_MANTIK.md) Entegrasyonu

Bu güncellemede `takas_analiz.py` aracı, ANA_MANTIK.md "anayasası" ile
tam uyumlu hale getirildi. Mevcut 4 modülün hiçbiri bozulmadı; üzerine
eksik özellikler eklendi. (918 satır → 1287 satır)

## YENİ EKLENENLER

### 1. GÜN GÜN ANALİZ + T+2 HİZALAMA (en büyük yeni özellik)
Yeni mod. AKD'nin T günü işlemleri, Hızlı Takas'a T+2 İŞ GÜNÜ sonra yansır.
Araç her AKD gününü doğru takas günüyle eşleştirir.

Kullanım:
    # Araç hizalar (dosya adında tarih olmalı: AKD_2026-03-15.csv):
    python3 takas_analiz.py --hisse ELITN \
      --gungun-akd AKD_2026-04-14.csv AKD_2026-04-15.csv \
      --gungun-takas TAKAS_2026-04-16.csv TAKAS_2026-04-17.csv

    # Kullanıcı zaten elle eşleştirdiyse:
    python3 takas_analiz.py --hisse ELITN --hizali \
      --gungun-akd a1.csv --gungun-takas t1.csv

Hizalama kuralı (anayasa):
  - Kullanıcı hizalamışsa (--hizali) → korunur
  - Kullanıcı hizalamamışsa → araç dosya adından T+2 iş günü hesaplar
  - Araç emin olamazsa (tarih okunamazsa) → SORAR, uydurmaz
NOT: İş günü takvimi şimdilik yalnız hafta sonunu atlıyor; BİST resmi
tatilleri sonra eklenecek (anayasada da not düşüldü).

### 2. HAM SENTEZ (aracın kalbi) — 5 soru → resim
Boyutları tek bir okunabilir resme bağlar:
  Soru1 oyuncu var mı → Soru2 kim → Soru3 evre → Soru4 gizli mi → Soru5 resim
Olgusal (karar yok) + ardından "çıkarım" (öneri, dayatma değil).
Tek-CSV ve iki-CSV modlarının sonunda otomatik çıkar.

### 3. "ALAN VAR SATAN YOK" ANOMALİSİ
İki-CSV modunda: tahtanın toplam satışı, toplam alışına göre çok küçükse
(< %30) → lot piyasadan değil dolaşıma giriş/bölünmeden gelmiş olabilir.
"Adet farkı = alım-satım değildir" uyarısının somutu.

### 4. CEP OLAYI ŞÜPHESİ
Çoklu aralık modunda: aynı kurum geçmişte düşük maliyetliyken son dönemde
çok daha yüksek maliyetten "yeni" görünüyorsa (≥1.30 kat) → maliyet
ilüzyonu (sağ cep-sol cep) şüphesi.

### 5. AKD OKUYUCU GENİŞLETİLDİ
Artık alış/satış toplamlarını da okuyor (anomali için). Net kolonu
yoksa eskisi gibi Alış−Satış ile çalışmaya devam ediyor.

## DEĞİŞMEYEN (korundu)
- Tek-CSV şüphe modu, iki-CSV kesin virman modu
- Çoklu aralık karşılaştırma (kalıcı/yoğun/yön değişimi)
- Koordine küme, çapraz doğrulama, defter/kayıt
- Patron çıkışı, eksi takas, hayat çizgisi, kategori filtresi
- "AL/SAT demez" ilkesi (her yerde)

## TEST DURUMU
4 modun hepsi gerçek CSV'lerle (ZGYO, ELITN) test edildi, çalışıyor.
Sözdizimi temiz.

## ÖNERİLEN COMMIT MESAJI
    git add takas_analiz.py ANA_MANTIK.md DEGISIKLIKLER.md
    git commit -m "Anayasa entegrasyonu: gun gun T+2, sentez, alan-satan anomalisi, cep olayi"
    git push
