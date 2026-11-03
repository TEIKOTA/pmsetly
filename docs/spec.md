# pmsetly 仕様（ドラフト）

MacBook の蓋を閉じても処理（AI エージェント等）を継続させるための、最小・無骨な macOS メニューバーアプリ。
OSS として公開リポジトリで配布する。

## 目的

- `sudo pmset -a disablesleep 1/0` の ON/OFF をメニューバーから 1 クリックで切り替える。
- 実際のシステム状態（`pmset -g` の `SleepDisabled`）を表示する。

## 設計原則（最優先）

- **コードを最小にし、誰でも数分で全部読めること**を機能より優先する。
  root 権限でシステム設定を変えるアプリなので、「読んで安心できる」ことが信頼の根拠になる。
- 依存ライブラリ 0。常駐 helper は持たない。system に残すのは sudoers の 1 ファイルだけで、`sudo rm` 1 回で消せる。
- 生成物・ストレージを最小にする。

## 機能（最小構成）

- メニューバーにアイコン 1 個（SwiftUI `MenuBarExtra`）。Dock 非表示。
- メニュー項目:
  - 状態表示: ON / OFF（実際の `SleepDisabled` 値）
  - トグル: スリープ防止の切り替え
  - 終了
- 状態取得: `pmset -g` の `SleepDisabled` 行を読む（観測例: `SleepDisabled\t\t1`）。
- 切り替え: `pmset -a disablesleep 1|0` を管理者権限で実行し、成功した場合のみ UI を更新する（UI は常に再取得した実状態を表示）。

## 技術

- Swift + SwiftUI `MenuBarExtra`（macOS 13 以降）。Xcode プロジェクトは持たず、SwiftPM ＋ 短い `build.sh` で `.app` を組み立てる。

## 配布

- ソースからビルドする。バイナリは配布しない（利用者は自分で読んだコードを自分でビルドするので、Gatekeeper の警告も出ない）。

## 管理者権限

- 初回だけ許可を与え、以後は `pmset` の切り替えだけをパスワードなしで実行する。
- `/etc/sudoers.d/pmsetly` に、`/usr/bin/pmset -a disablesleep 0` と `/usr/bin/pmset -a disablesleep 1` の 2 コマンドだけを完全一致で NOPASSWD 許可する。アプリは `sudo -n` で実行する。
- 受け入れたリスク: そのユーザーで動くプロセスは、パスワードなしでスリープ防止を切り替えられる（影響はスリープ設定だけ）。
- 設定は repo の `install.sh` で入れる。`.app` を `/Applications` に置き、`visudo -c` で検証した sudoers を書く。利用者は中身を読んでから自分で `sudo` 実行する。
- 許可の対象は install.sh を実行したユーザー 1 人だけ（`%admin` にはしない）。
- 未設定（`sudo -n` が失敗）のときは、メニューに「install.sh を実行してください」と表示するだけにする。アプリ自身は root でファイルを書かない。
- アンインストールは README に 2 コマンドで書く（`sudo rm /etc/sudoers.d/pmsetly` と `.app` の削除）。

## 終了と異常終了

- 正常終了: 実状態が 1 なら `disablesleep 0` を実行してから終了する。起動前の値は記憶しない。
- 異常終了: 専用の対策はしない。再起動すれば実状態の ON が表示されるので、そこで OFF にできる。README に復旧コマンド `sudo pmset -a disablesleep 0` を書く。

## 非目標

- タイマー・バッテリー残量による自動解除
- Caps Lock 監視、設定ウィンドウ
- ログイン時起動
- 発熱・バッテリーの監視（README で注意喚起のみ）

## 既定で進める事項

- アイコンは SF Symbols の 2 種類で ON/OFF を表す。メニューを開くたびに実状態を読み直す。
- テストは `pmset -g` の出力を解析する関数だけに付ける。
- 発熱とバッテリーの注意は README に書く。

## Open Questions（未確定）

- なし（2026-11-03 合意済み）
