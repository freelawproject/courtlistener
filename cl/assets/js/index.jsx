import React from 'react'

const App = () => {
  return (
    <div>
      <h1>Hello, Mike!</h1>
      <h3>This is my new react app!</h3>
    </div>
  )
}

React.render(<App/>, document.getElementById('react-root'))