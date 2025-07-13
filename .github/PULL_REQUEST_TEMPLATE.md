## Summary

What does this fix, how did you fix it, what approach did you take, what gotchas are there in your code or compromises did you make?


## Fixes

What bugs does this fix? Use the [correct syntax to auto-close the issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue#linking-a-pull-request-to-an-issue-using-a-keyword).


## Deployment

1. The following labels control the deploymnet of this PR if they are applied. Please choose which should be applied, then apply them to this PR:

   - [ ] <kbd>skip-deploy</kbd> — The entire deployment can be skipped.

        This might be the case for a small fix, a tweak to documentation or something like that.

   - [ ] <kbd>skip-web-deploy</kbd> — The web tier can be skipped.

        This is the case if you're working on code that doesn't affect the front end, like management commands, tasks, or documentation.

   - [ ] <kbd>skip-celery-deploy</kbd> — Deployment to celery can be skipped.

        This is the case if you make no changes to tasks.py or the code that tasks rely on.

   - [ ] <kbd>skip-cronjob-deploy</kbd> — Deployment to cron jobs can be skipped.

        This is the case if no changes are made that affect cronjobs.

1. What extra steps are needed to deploy this beyond the standard deploy?

    Do scripts need to be run or things like that?

    If this is more than a quick thing, a [new issue should be created in our infra repo]([url](https://github.com/freelawproject/infrastructure/issues/new)). (If you do not have access to it, just put the steps here.)


## Screenshots

If this changes the front end, please include desktop and mobile screenshots or videos showing the new feature.

<details>
<summary>Desktop</summary>

YOUR IMAGE(S) HERE

</details>


<details>
<summary>Mobile</summary>

YOUR IMAGE(S) HERE

</details>
