# Build from the extracted source directory: makepkg -si
pkgname=steambridge
pkgver=0.2.0
pkgrel=1
pkgdesc='Steam Controller 2026 to virtual Xbox gamepad, with desktop controls'
arch=('any')
license=('MIT')
depends=('python' 'python-evdev' 'tk' 'systemd')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')
options=('!debug')
source=()
sha256sums=()

build() {
  cd "$startdir"
  python -m build --wheel --no-isolation
}

check() {
  cd "$startdir"
  python -m unittest discover -s tests -v
}

package() {
  cd "$startdir"
  python -m installer --destdir="$pkgdir" dist/steambridge-0.2.0-py3-none-any.whl
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -Dm644 packaging/70-steambridge.rules "$pkgdir/usr/lib/udev/rules.d/70-steambridge.rules"
  install -Dm644 packaging/steambridge.conf "$pkgdir/usr/lib/modules-load.d/steambridge.conf"
  install -Dm644 packaging/steambridge.desktop "$pkgdir/usr/share/applications/steambridge.desktop"
  install -Dm644 packaging/steambridge.service "$pkgdir/usr/lib/systemd/user/steambridge.service"
}
