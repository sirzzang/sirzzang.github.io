source "https://rubygems.org"

gem "minimal-mistakes-jekyll"

gem "jekyll", "~> 3.6.2"

gem "github-pages", "~> 168"
gem "rake", "~> 12.3.0"

# Ruby 3.0+ 에서 stdlib 기본 gem 에서 분리됨 — 로컬 빌드용으로 명시 추가
gem "webrick"   # jekyll serve (Ruby 3+)
gem "rexml"     # kramdown 1.14 가 require
# Ruby 3.1 기본 Psych 4 는 YAML.load 시그니처가 바뀌어 jekyll 3.6 front matter 파싱이 깨짐 → 3.x 로 고정
gem "psych", "~> 3.3"
gem "tzinfo-data"
gem "wdm", "~> 0.1.0" if Gem.win_platform?

group :jekyll_plugins do
  gem "jekyll-feed"
  gem "jekyll-seo-tag"
  gem "jekyll-sitemap"
  gem "jekyll-paginate"
  gem "jekyll-algolia"
  gem "jekyll-include-cache"
  gem "jekyll-gist"
  gem "jemoji"
end