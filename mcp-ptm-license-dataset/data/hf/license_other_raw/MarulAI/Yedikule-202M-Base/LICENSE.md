# Yedikule Model Lisansı

Sürüm 2.0

Telif hakkı sahibi: **Ahmet Karakuş** (Marul AI)

## Kısaca

Modeli özgürce kullanabilir, üzerine kendi modelinizi eğitebilir ve paylaşabilirsiniz. Üç şartla: ticari kullanım için izin alın, Yedikule'ye atıf yapın, türev modelinizin adında Yedikule geçsin.

## 1. Kapsam

Bu lisans Yedikule modelinin şu bileşenlerini kapsar:

- Model ağırlıkları ve bunlardan türetilen her biçim (GGUF, ONNX, nicelenmiş sürümler, ince ayar sonucu ağırlıklar, birleştirilmiş modeller)
- Tokenizer ve sözlüğü
- Model mimarisi kodu (`model.py`, `config.py`)
- Yapılandırma dosyaları ve dokümantasyon

Bunların tamamı bundan sonra "Model" olarak anılır. Model üzerindeki fikri mülkiyet hakları Ahmet Karakuş'a aittir.

## 2. İzin verilen kullanım

Aşağıdakiler için ayrıca izin almanıza gerek yoktur. Hepsi ticari olmayan kullanımla sınırlıdır ve 3. bölümdeki şartlara tabidir.

**2.1 Kullanım.** Modeli kendi cihazınızda veya sunucunuzda çalıştırabilirsiniz.

**2.2 Eğitim ve araştırma.** Ders, atölye, tez, akademik araştırma ve ölçüt çalışmalarında kullanabilirsiniz.

**2.3 Yeniden eğitim ve türev model.** Model üzerinde ince ayar (fine-tuning) yapabilir, sürekli eğitimle geliştirebilir, LoRA veya benzeri adaptör ekleyebilir, damıtabilir, başka modellerle birleştirebilirsiniz. Ortaya çıkan modeli yayımlayabilirsiniz.

**2.4 Biçim dönüştürme.** Modeli GGUF, ONNX ve benzeri biçimlere çevirebilir, niceleyebilir (Q4, Q8 ve diğerleri) ve bu dosyaları paylaşabilirsiniz.

**2.5 Yeniden dağıtım.** Modeli olduğu gibi veya değiştirilmiş halde başka platformlarda yayımlayabilirsiniz.

## 3. Şartlar

İzin verilen kullanımların tamamı aşağıdaki şartlara bağlıdır.

**3.1 Atıf.** Modeli kullandığınız veya ondan türettiğiniz her yerde Yedikule'ye ve geliştiricisine atıf yapmalısınız. Yayımladığınız model kartında, dokümantasyonda veya akademik yayında şu bilgi bulunmalıdır:

```
Bu çalışma Yedikule modeline dayanmaktadır.
Yedikule, 202M parametreli Türkçe dil modeli.
Ahmet Karakuş, Marul AI, 2026.
```

**3.2 İsim.** Yedikule'den türettiğiniz bir modeli yayımlarsanız, modelin adında **Yedikule** geçmelidir. Örnek: `Yedikule-Tip`, `Yedikule-Kod`, `Firma-Yedikule-Asistan`. Modelin Yedikule'den türediğini gizleyemez, kendi sıfırdan eğitiminiz gibi sunamazsınız.

**3.3 Türevler de bu lisansa tabidir.** Bu modelden türetilen her çalışma (ince ayar, sürekli eğitim, adaptör, damıtma, birleştirme, niceleme, biçim dönüşümü ve benzeri) bu lisansın kapsamındadır ve aynı koşullara bağlıdır. Türev modelinizi dağıtırken bu lisans dosyasını da birlikte vermeniz zorunludur. Türev modelinize daha gevşek bir lisans veremez, kendi lisansınızla yeniden lisanslayamazsınız. Bu yükümlülük türevin türevi için de sürer.

**3.4 Telif bilgisinin korunması.** Telif hakkı beyanını ve geliştirici bilgisini kaldıramaz veya değiştiremezsiniz.

## 4. Ticari kullanım

Ticari kullanım, telif hakkı sahibinin yazılı izni olmadan yasaktır. Ticari kullanım şunları kapsar:

- Modeli doğrudan veya dolaylı gelir getiren bir ürüne veya hizmete gömmek
- API olarak ücretli sunmak, abonelik veya reklam geliri elde etmek
- Kurum içi ticari süreçlerde çalıştırmak
- Modelden türetilmiş bir modeli ticari amaçla kullanmak veya satmak
- Danışmanlık hizmetinde kullanmak

Ticari kullanım için telif hakkı sahibinden izin alın. Talebinizi şu adrese gönderin:

**marulai.resmi@gmail.com**

Talepler ayrıca değerlendirilir ve yazılı sözleşmeye bağlanır. Bu, modelden türetilmiş modellerin ticari kullanımı için de geçerlidir; türev modeli siz eğitmiş olsanız bile ticari kullanım izne bağlıdır.

Akademik araştırma, kişisel projeler, öğrenme ve açık kaynak topluluk çalışmaları ticari kullanım sayılmaz.

## 5. Eğitim verisi

Model, kısmen `uonlp/CulturaX` kümesinin Türkçe alt kümesinden, kısmen de telif hakkı sahibinin kendi web taramasından derlenen bir corpus üzerinde eğitildi. CulturaX bölümü olduğu gibi kullanılmadı; ayrıca filtrelendi ve derin bir temizlik aşamasından geçirildi.

CulturaX'in kendine ait bir lisansı yoktur, kaynaklarının koşullarını devralır: lisans koşulları `mC4` ve `OSCAR` kümelerini takip eder ve her ikisi de Common Crawl üzerinden üretilmiştir. Bu koşullar bu lisanstan bağımsız olarak yürürlüktedir.

Modeli ticari amaçla kullanmak isteyen taraf, telif hakkı sahibinden izin almanın yanında mC4, OSCAR ve Common Crawl koşullarının kendi kullanım biçimine uygunluğunu ayrıca değerlendirmelidir. Telif hakkı sahibinin verdiği ticari izin, kaynak veri koşullarından doğan yükümlülükleri ortadan kaldırmaz.

## 6. Yasaklar

**6.1** İzinsiz ticari kullanım.

**6.2** Modeli veya türevini, Yedikule kaynaklı olduğunu gizleyerek sunmak.

**6.3** Telif hakkı beyanını, lisans dosyasını veya geliştirici bilgisini kaldırmak.

**6.4** Modeli yasa dışı içerik üretmek, kişileri hedef almak, yanıltıcı bilgi yaymak veya zarar verecek biçimde kullanmak.

## 7. Garanti reddi

Model olduğu gibi sunulur. Telif hakkı sahibi, Modelin belirli bir amaca uygunluğu, kesintisiz çalışması veya ürettiği bilginin doğruluğu konusunda garanti vermez.

Model istatistiksel bir dil modelidir; yanlış, eksik veya yanıltıcı bilgi üretebilir. Tıbbi, hukuki, finansal veya güvenlik açısından kritik kararlarda tek başına kullanılmamalıdır. Çıktıların doğrulanması kullanıcının sorumluluğundadır.

## 8. Sorumluluğun sınırlandırılması

Telif hakkı sahibi, Modelin kullanımından doğan doğrudan veya dolaylı hiçbir zarardan sorumlu tutulamaz. Modeli kullanan taraf, kullanımdan doğacak tüm hukuki ve mali sorumluluğu kabul eder.

## 9. Lisansın feshi

Bu lisansın şartlarını ihlal etmeniz durumunda kullanım izniniz kendiliğinden sona erer. İhlali öğrendikten sonra otuz gün içinde düzeltirseniz izniniz geri kazanılır. Fesih, ihlal nedeniyle doğan hukuki sorumluluğu ortadan kaldırmaz.

## 10. Uygulanacak hukuk

Bu lisans Türkiye Cumhuriyeti hukukuna tabidir. Uyuşmazlıklarda İstanbul mahkemeleri ve icra daireleri yetkilidir.

## 11. İletişim

Ticari lisans, izin talepleri ve ihlal bildirimleri için:

Ahmet Karakuş, Marul AI
marulai.resmi@gmail.com

---

## English summary

This is a non-binding summary. The Turkish text above is the governing license.

Copyright Ahmet Karakuş (Marul AI).

**You may**, without asking: run the model, use it for education and research, fine-tune it, distill it, merge it, quantize it, convert it to other formats, and publish the result. All of this is limited to non-commercial use.

**You must**: give attribution to Yedikule and its developer; include the name **Yedikule** in the name of any derivative model you publish; ship this license with the model or any derivative; keep the copyright notice intact. Any derivative work remains subject to this same license and cannot be relicensed under different terms.

**You may not**, without written permission: use the model or any derivative commercially; present the model as your own work or hide that it derives from Yedikule; remove the license or copyright notice; or use it for illegal, harmful or deceptive purposes.

Provided as is, without warranty. Contact the copyright holder for commercial licensing: Ahmet Karakuş, Marul AI, marulai.resmi@gmail.com
