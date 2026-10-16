# Arch package (`ai-toolbox-git`)

Build and install locally:

```sh
makepkg -si
```

If `python` on your PATH is not the system one (mise, pyenv, conda), build
with `env PATH=/usr/bin:/bin makepkg -si`.

## Publishing to the AUR

One time: create an account on https://aur.archlinux.org and add your SSH
public key under *My Account*. Then:

```sh
git clone ssh://aur@aur.archlinux.org/ai-toolbox-git.git /tmp/aur-ai-toolbox
cp PKGBUILD .SRCINFO /tmp/aur-ai-toolbox/
cd /tmp/aur-ai-toolbox
git add PKGBUILD .SRCINFO
git commit -m "Initial import"
git push
```

After changing the PKGBUILD, regenerate `.SRCINFO` with
`makepkg --printsrcinfo > .SRCINFO` and push again. A `-git` package does not
need a push for every upstream commit: `pkgver()` reads it at build time.
