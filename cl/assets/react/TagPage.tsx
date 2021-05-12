import React, {useState} from "react";
import MarkdownView from "react-showdown";
import {Converter} from "showdown";
import {updateTags} from "./_useTags";
import {
  Tabs, Tab, TabContainer, ButtonToolbar, DropdownButton, MenuItem, Button,
} from 'react-bootstrap';
import "./tag-page.css";
import Switch from 'react-input-switch';
import {Tag} from "./_types";
import MdEditor from 'react-markdown-editor-lite';
import 'react-markdown-editor-lite/lib/index.css';

type CLData = {
  title: string;
  user: string;
  viewCount: number;
  dateCreatedDate: string;
  description: string;
  id: number;
  name: string;
  pageOwner: string;
  published: string;
}

type markdown_opts = {
  autoRefresh: boolean;
  spellChecker: boolean;
  uploadImage: boolean;
  placeholder: string;
  maxHeight: string;
  minHeight: string;
  sideBySideFullscreen: boolean;
  status: boolean;
  toolbar: any;
}

const markdown_options: markdown_opts = {
  autoRefresh: true,
  spellChecker: false,
  uploadImage: false,
  placeholder: "Add your description here...",
  maxHeight:"400px",
  minHeight:"400px",
  sideBySideFullscreen: false,
  status: false,
  toolbar: [
    'bold', 'italic', 'heading', '|', 'quote', 'code', 'horizontal-rule',
    'unordered-list', 'ordered-list', 'table', 'link', '|', 'side-by-side',
    {
      name: 'guide',
      action () {
          const win = window.open('https://www.courtlistener.com/help/markdown/', '_blank');
          if (win) { win.focus();
        }
      },
      className: 'fa fa-info-circle',
      title: 'Markdown Syntax',
      },
    ],
  }

const PageTop = (data: CLData) => {
  return (
    <React.Fragment>
    <div className="row">
        <div className="col-md-2">
          <h1 className="clearfix"><span className="tag">{data.name}</span></h1>
        </div>
      </div>
      <p>Created by
        <a className="alt tag-back" href={`/tags/${data.user}/`}> {data.user}</a> on
        <span className="alt"> {data.dateCreatedDate}</span> with {data.viewCount}
      </p>
    </React.Fragment>
  )
}

const TagOptions = (data: CLData) => {
  const {modifyTags, deleteTags} = updateTags();
  const [isPublic, setPublic] = useState((data.published == 'True'));

  const delete_tag = (tag_id: number) => {
    if (window.confirm('Are you sure you want to delete this item?')) {
      deleteTags(tag_id)
      // Relocate to the previous page on delete
      let url = window.location.href.slice(0, -1)
      window.location.href = url.substr(0,url.lastIndexOf('/')+1)
    }
  }

  function toggle_menu(published: boolean, name: string, id: number ){
    modifyTags({published: !published, name: name, id: id} as Tag)
    setPublic(!published)
  }

  return (
    <div>
      <div id={"tag-settings-parent"} className="float-right v-offset-above-1">
        <ButtonToolbar>
          <DropdownButton pullRight
          className={"fa fa-gear gray"}
          bsSize="large"
          noCaret
          title=""
          id="tag-settings">
            <li role="presentation"
                value={+isPublic}
                onClick={e => toggle_menu(isPublic, `${data.name}`, Number(`${data.id}`))}
                className="">
              <a role="menuitem"
                 href="#">
                <Switch value={+isPublic} />
                &nbsp;Is Publicly Available
              </a>
            </li>
          <MenuItem divider />
          <MenuItem
            checked={true}
            onClick={_ => delete_tag(Number(`${data.id}`))}
          eventKey="4"><i className="fa fa-trash gray"></i>&nbsp;Delete</MenuItem>
          </DropdownButton>
        </ButtonToolbar>
      </div>
    </div>
  )
}

const TagMarkdown = (data: CLData) => {
  const { modifyTags, deleteTags } = updateTags();
  const [text, setText] = useState(data.description)
  const [key, setKey] = useState('write');
  const [disabled, setDisabled] = useState(true);

  function save_on_select(k: any) {
    if (k !== key){
      if (k == "write") {
        let tag = {
          description: text, name: data.name as string, id: data.id as number
        } as Tag
        modifyTags(tag).then(_ => {
          setDisabled(true)
        })
      }
    }
    setKey(k)
  }

  function save_button() {
    let tag = {
      description: text,
      name: data.name as string,
      id: data.id as number
    } as Tag
    modifyTags(tag).then(_ => {
      setDisabled(true)
    })
  }

  function update({html, text}) {
    setText(text)
    setDisabled(false)
  }

  if (data.pageOwner == "False") {
    if (text == "") {
      return <div><PageTop {...data}/></div>
    }
    return (
      <div>
        <PageTop {...data}/>
        <div id="markdown_viewer" className="col-12 view-only">
          <MarkdownView markdown={text || ""}
            flavor={"github"}
            options={{ tables: true, emoji: true, simpleLineBreaks: true}}/>
        </div>
      </div>
    )
  }
  const convert = new Converter({ tables: true, emoji: true, simpleLineBreaks: true})

  return (
    <div>
      <TagOptions {...data} />
      <PageTop {...data}/>
      <TabContainer id="tab-tabs" defaultActiveKey="first">
        <Tabs
          id="controlled-tab-example"
          activeKey={key}
          onSelect={save_on_select}>
          <Tab eventKey="write" title="Notes">
            <div id="markdown_viewer" className="col-12">
            <MarkdownView markdown={text || ""} flavor={"github"} options={{ tables: true, emoji: true, simpleLineBreaks: true}}/>
          </div>
          </Tab>
          <Tab eventKey="preview" title="Edit">
              <MdEditor value={text} onChange={update}
                        style={{height: "500px"}}
                        renderHTML={(text: string) => convert.makeHtml(text)}/>
            <span id={"save_span"} style={{"float": "right"}}><Button disabled={disabled} id={'save_button'} onClick={save_button} className={"whitesmoke"}><i className={"fa fa-save"}/> Save</Button></span>
          </Tab>
        </Tabs>
      </TabContainer>
    </div>
  )
}

export {TagMarkdown}
