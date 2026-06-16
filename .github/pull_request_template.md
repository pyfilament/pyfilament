# context

what is the background for needing to make this change? write this section to provide historical context for future readers.
some examples:
  the change was needed to resolve [a bug](link to bug report)
  this introduces a [new feature](link to tech spec doc)
  this is a part of major refactoring(link to tech spec doc)

# changes

write one sentence for each change that was included.
some examples:
  updated button css for writing text from blue to green
  added new functions for generating next thoughts
  added new database table for react blocks
  moved function from foo.js to bar.js

# tests

write the exact steps to follow to test the change
be sure to include separate sections for behavior before and after the test

example:

```
from filament import task

@task
async def foo():
    return 'foo'

async def test_foo():
    assert foo() == 'foo'
```

include any stack traces in their entirety

ui example:
  1. click on homepage
  2. click on product page
  3. click on inspect product button on the bottom
  before: browser renders 500 server error
  after: inspect product overlay renders correctly (include screenshot)
