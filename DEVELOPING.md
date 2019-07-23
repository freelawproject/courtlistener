# Developing in CourtListener

CourtListener is built upon a few key pieces of technology that needs to come together in order to function. Whether you're contributing platform code, web design, etc. it helps to know the easiest ways to run and test the project.

The best way to get started is to configure your own Ubuntu Linux environment to support running CourtListener per the [wiki instructions][wiki].


# Workflow

For the most part, we use [Github flow][flow] to get our work done. Our 
[BDFL][bdfl] and primary developer is [@mlissner][me]. For better and/or for worse, 
he doesn't care too much about git, provided things get done smoothly and his 
life is fairly easy. What that means generally, is:

1. Commits should represent a unit of work. In other words, if you're working 
on a big feature, each commit should be a descrete step along the path of 
getting that feature ready to land. Bad or experimental work shouldn't be in a
commit that you submit as part of a PR, if you can avoid it. 

1. Your commit messages should use [the format defined by the Angular.js 
project][format]. This is pretty easy if you use [this plugin][format-plugin] 
for Intellij/PyCharm/et al.

1. If you want to change whitespace, do it in its own commit and ideally in its
own PR. We encourage code cleanup and whitespare/reformatting is part of that, 
BUT the more isolated it is from other changes, the better. When whitespace is
combined with other code changes, the PR's become impossible to read and risky
to merge. 

    A suggestion: If this stuff bugs you, do a round of whitespace/formatting 
    cleanup before you start on each file and/or once you're done.  

1. *KEEP YOUR PR's SMALL*. A good PR should land a specific thing of some sort. 
It doesn't have to be done — it doesn't even have to work! — but it should be 
clean and it should be your best effort at clean *progress*. PRs are both a way
of getting your work into the system and a way to *communicate* your work. The
latter is more important. 10 small, clean PRs are about 10× better than a 
monolithic one that is fully functional. 

    Say you are developing a system that relies on regexes to do something. Why
    not submit the regexes (and their tests!) in one PR and the thing that uses
    those regexes in another? That'd be much easier to review than trying to 
    see the whole thing at once. 
    
These guidelines are a little sloppy compared with many projects. Those 
projects have greater quality needs, are popular enough to demand a high 
bar, and can envision coding techniques as a part of their overall goal. We 
don't have to lead the industry with our approach, we just need to get good 
work done. That's the goal here. 

[me]: https://github.com/mlissner
[flow]: https://guides.github.com/introduction/flow/
[bdfl]: https://en.wikipedia.org/wiki/Benevolent_dictator_for_life
[format]: https://github.com/angular/angular.js/blob/master/DEVELOPERS.md#-git-commit-guidelines
[format-plugin]: https://plugins.jetbrains.com/plugin/9861-git-commit-template/


# Testing

Any time you're contributing to or hacking on code base, whether adding features or fixing issues, you should validate your changes don't break the core functionality of CourtListener by executing the test suite. This is also a great way to validate your development environment is properly configured. (You should probably consider adding your own tests as well!)

In general, the easiest way to run the test suite is via Django's `test` command. An example from within the FreeLawBox images:

```bash
>(courtlistener)vagrant@freelawbox64:/var/www/courtlistener$ ./manage.py test --noinput cl
```

The `--noinput` flag tells Django to destroy any old test databases without prompting for confirmation (typically this is what you want).

The `cl` parameter is the name of the Python package to search for tests. It's not required, but a good habit to learn as you can more specifically specify tests by provided more details, such as `cl.search` to execute only tests in the search module.

For more details, Django provides a lot of documentation on [testing in Django][django-testing]. Make sure to read the docs related to the current release used in CourtListener. (As of 27-01-2017, that's v1.8.7.)

## About the Types of Tests

There are a few different types of tests in the CourtListener test suite and can be generally categorized as follows in increasing complexity:
* **Unit Tests** that exercise core application logic and may require some level of access to the Django test database,
* **Solr Tests** that rely on the Apache Solr test cores to be online and have documents indexed for test execution,
* **Selenium Tests** that rely on the full-stack of Django, the database, and Solr to be available in order to test from the point of view of a web browser accessing the application.

### Unit Tests

Unit tests should derive from `unittest.TestCase` or `django.test.TestCase` and run without a functioning Solr environment or Selenium functioning. These are the bread and butter of validating functions and business logic. You should contribute these when you write any new functions or update them when enhancing existing functions.

### Solr Tests

Solr/search tests should derive from `cl.search.tests.EmptySolrTestCase` and use appropriate setup/teardown methods to populate the index by either manually creating model instances and passing the `index=True` attribute when calling `.save()` or calling the provided `cl.search.management.commands.cl_update_index` Django management command that will index the models from the database into the Solr cores.

### Selenium Tests

Selenium tests should derive from `cl.tests.base.BaseSeleniumTest`, which automatically handles the setup and teardown of a Selenium webdriver instance available at `self.browser` from within your test code.

There are some helper methods provided via `BaseSeleniumTest` as well:
* `reset_browser()` - start a new browser session
* `click_link_for_new_page(link_text, timeout)` - a wrapper around the Selenium functions for finding an anchor based on the anchor text and calling click(), but also does an explicit wait up until _timeout_ seconds for the browser page to change. Use when expecting a navigation event.
* `attempt_sign_in(username, password)` - from a given CL page, will attempt to use the _Sign in / Register_ link and input the given username and password.
* `get_url_and_wait(url, timeout)` - will input the given url into the browser's address bar, submit, and wait until _timeout_ seconds for the given url to load.
* `assert_text_in_body(text)` - attempts to find the given text in the body of the current web page, failing the test if not found
* `assert_text_not_in_body(text)` - similar to previous, but tests that text is NOT in the body, failing if it's found.
* `extract_result_count_from_serp()` - if on the search result page, will attempt to find and parse the total results found count into a number and return it.

## Running the Test Suite

If you're going to run the full test suite, you might need to pre-configure some environment variables to assist in the Selenium test execution.

### Selenium Tests when Headless

If you're using the FreeLawMachine in headless mode (e.g. you only SSH into the machine, there's no visible desktop environment), you need to do a few additional steps to run the Selenium tests without fail:

1. Install [Chrome](https://google.com/chrome) or [Chromium](https://www.chromium.org) on your local machine
2. Install or upgrade [chromedriver][] on your local machine
3. Launch **chromedriver** either as a service or just from a command line. The following example will start it ready to receive input from any host:
    ```bash
    chromedriver --whitelisted-ips
    ```
4. In your FreeLawBox or similar VM, configure some environment properties. In Linux, you can use the `export` command like so: `export PROPERTY=value`
  * `DJANGO_LIVE_TEST_SERVER_ADDRESS=0.0.0.0:8081`
  * `SELENIUM_REMOTE_ADDRESS=10.0.2.2:9515`
5. Run the test suite as normal.

If the above is working, you should see Selenium use your local copy of Chrome/Chromium to run the tests (i.e. the one NOT in the VM but on your host laptop/desktop).

If you have issues, check the following:
* **SELENIUM_REMOTE_ADDRESS**
  * From within your VM, check for the gateway IP address. In Linux, run `netstat -r` and get the gateway IP from the routing table.
  * For the port number, make sure it matches the port number printed by **chromedriver** when you start it. The default should be `9515`
* **DJANGO_LIVE_TEST_SERVER_ADDRESS**
  * This should "just work" when set to `0.0.0.0:8081`. Make sure you didn't use `localhost` or `127.0.0.1` as for some reason that doesn't always work!
  * If you're not using the provided FreeLawBox, make sure you have port forwarding configured in your VM such that port 8081 is being forwarded to your host machine's port 8081. See the [vagrant port forwarding docs][vagrant-ports] for more details.

### Increasing the Test Timeouts

The Selenium tests are wrapped with a timeout annotation that will fail them if they take too long to run. If you need to increase, or even want to decrease, this value then the easiest step is to set the `SELENIUM_TIMEOUT` environment variable to the given time in seconds.

For example, for a 2 minute timeout, you might do the following on Linux (or within the FreeLawBox):

```bash
export SELENIUM_TIMEOUT=120
```

### Taking Screenshots on Failure

While a little flaky at the moment, most Selenium tests will be able to take a screenshot of the browser window on a failure. This should work well when running the FreeLawBox Desktop version (i.e. NOT in headless mode).

To enable screenshots, simply define a `SELENIUM_DEBUG` environment variable set to anything. It's presence indicates it's enabled.

```bash
export SELENIUM_DEBUG=1
```

You should find screenshot files available in the project directory. It's recommend you run the test suite with the `--failfast` option so it stops executing the rest of the tests if it encounters a failure. Currently, the screenshot is named after the test class and you may overwrite a screenshot if you continue through more tests in the same class.

## CI/CD

This Github project is configured to run tests for every pull request.
A webhook triggers [CircleCI][circleci-cl-builds] to run `.circleci/config.yml`.
`config.yml` makes CircleCI run tests inside a Docker container. The custom
Docker image used to run tests is built from `.circleci/Dockerfile` and pushed
to [Docker Hub][hub-cl-testing].

### Updating the testing container

If you add new dependencies, remember to update the testing container with the following steps.

1. Have `docker` and `make` CLI tools installed.
2. Have a Docker Hub account that's a member of the [freelawproject organization][hub-flp].
3. `docker login` with your credentials for the Hub account above.
4. Set the version in `version.txt` to whatever makes sense according to
   semantic versioning. Most of the time incrementing the patch version is enough.
   Also remove `-SNAPSHOT`.
5. `make push --file .circleci/Makefile` 
6. Use new Docker image in CircleCI tests by updating the [tag in config.yml][circleci-test-container-tag].
7. Wait for the build to finish, **then** increment `version.txt` and
   append `-SNAPSHOT` to the version string to prepare for the next SNAPSHOT
   release. This is to prevent someone from accidentally overwriting a stable
   release.


[wiki]: https://github.com/freelawproject/courtlistener/wiki/Installing-CourtListener-on-Ubuntu-Linux
[chromedriver]: https://sites.google.com/a/chromium.org/chromedriver/downloads
[django-testing]: https://docs.djangoproject.com/en/1.8/topics/testing/
[vagrantfile]: https://raw.githubusercontent.com/freelawproject/freelawmachine/master/Vagrantfile
[vagrantfile-desktop]: https://github.com/freelawproject/freelawmachine/blob/master/Vagrantfile.desktop
[flm]: https://github.com/freelawproject/freelawmachine
[flm-readme]: https://github.com/freelawproject/freelawmachine/blob/master/README.md
[vagrant-ports]: https://www.vagrantup.com/docs/networking/forwarded_ports.html
[circleci-cl-builds]: https://circleci.com/gh/freelawproject/courtlistener
[hub-cl-testing]: https://hub.docker.com/r/freelawproject/courtlistener-testing/
[hub-flp]: https://hub.docker.com/u/freelawproject/dashboard/
[circleci-test-container-tag]: https://github.com/freelawproject/courtlistener/blob/360c259f7d427700c2de9bf8fd53a73a33ff2eed/.circleci/config.yml#L5
