IMAGE ?= pr-review:local
JSON  ?= examples/dotfiles-pr6.json

.PHONY: image validate render example clean help

help:
	@echo "make image     build the review container"
	@echo "make validate  JSON=<f>  structural check, no render"
	@echo "make render    JSON=<f>  render to <f>.html"
	@echo "make example   render the bundled PR #6 example"

image:
	docker build -t $(IMAGE) .

# Validation is pure stdlib, so it runs anywhere; rendering a page you already
# annotated does not need the container.
validate:
	@python3 scripts/render-review.py $(JSON) -o /dev/null && echo "ok: $(JSON)"

render:
	@python3 scripts/render-review.py $(JSON)

example: render

clean:
	rm -rf .pr-review examples/*.html
