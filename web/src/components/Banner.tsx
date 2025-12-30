import { Card } from './ui/card'

export function Banner() {
  return (
    <Card className="w-full p-6 mb-6 bg-gradient-to-r from-blue-500 to-purple-600 text-white border-none">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-2">Welcome to the Contoso AG-UI Clinic!</h1>
        <p className="text-sm opacity-90">Your intelligent assistant is ready to help</p>
      </div>
    </Card>
  )
}
